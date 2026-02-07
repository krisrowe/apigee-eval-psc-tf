locals {
  environments = {
    dev = {}
  }
  envgroups = {
    eval-group = ["dev"]
  }

  # Auto-derive hostname from CLI config: {project_nickname}.{default_root_domain}
  derived_hostname = try(
    var.default_root_domain != null && var.default_root_domain != ""
    ? "${var.project_nickname}.${var.default_root_domain}"
    : null,
    null
  )

  # Final hostname fallback chain:
  # 1. Explicit var.domain_name from tfvars (highest priority)
  # 2. Derived from CLI config default_root_domain (passed as var)
  # 3. null (IP-only access, will trigger warning)
  hostname = try(coalesce(var.domain_name, local.derived_hostname), null)
}


# Validation: warn if no hostname is configured
resource "null_resource" "hostname_warning" {
  count = local.hostname == null ? 1 : 0

  provisioner "local-exec" {
    command = "echo 'WARNING: No domain_name configured. Apigee will only be accessible via IP address. Set domain_name in tfvars or configure default_root_domain via: ./util config set default_root_domain example.com'"
  }
}

resource "null_resource" "project_label" {
  provisioner "local-exec" {
    command = "gcloud projects update ${var.gcp_project_id} --update-labels=apigee-tf=${var.project_nickname}"
  }
}

data "google_project" "project" {
  project_id = var.gcp_project_id
}

resource "google_project_service" "apigee" {
  project = var.gcp_project_id
  service = "apigee.googleapis.com"
}

resource "google_project_service" "cloudkms" {
  project = var.gcp_project_id
  service = "cloudkms.googleapis.com"
}

resource "google_project_service" "compute" {
  project = var.gcp_project_id
  service = "compute.googleapis.com"
}

resource "google_project_service" "servicenetworking" {
  project = var.gcp_project_id
  service = "servicenetworking.googleapis.com"
}

resource "google_project_service" "dns" {
  project = var.gcp_project_id
  service = "dns.googleapis.com"
}


resource "google_compute_network" "apigee_network" {
  name                    = "apigee-network"
  project                 = var.gcp_project_id
  auto_create_subnetworks = true
  depends_on              = [google_project_service.compute]
}

resource "google_apigee_organization" "apigee_org" {
  project_id       = var.gcp_project_id
  analytics_region = var.control_plane_location != null && var.control_plane_location != "" ? "" : var.apigee_analytics_region

  # Dynamic Data Location Logic
  api_consumer_data_location = var.control_plane_location != null && var.control_plane_location != "" ? var.apigee_analytics_region : null

  runtime_type = "CLOUD"

  # HARDCODED AS REQUESTED
  billing_type = "PAYG"

  disable_vpc_peering = true

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    google_project_service.apigee,
    google_project_service.cloudkms,
    google_project_service.compute,
    google_project_service.servicenetworking,
    google_project_service.dns,
  ]
}


resource "google_apigee_instance" "apigee_instance" {
  name     = var.apigee_runtime_location
  location = var.apigee_runtime_location
  org_id   = google_apigee_organization.apigee_org.id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_apigee_environment" "apigee_env" {
  for_each = local.environments
  name     = each.key
  org_id   = google_apigee_organization.apigee_org.id
  type     = "COMPREHENSIVE"
}

resource "google_apigee_envgroup" "envgroup" {
  for_each  = local.envgroups
  name      = each.key
  org_id    = google_apigee_organization.apigee_org.id
  hostnames = local.hostname != null ? [local.hostname] : []
}

resource "google_apigee_envgroup_attachment" "envgroup_attachment" {
  for_each = {
    for pair in flatten([
      for eg, envs in local.envgroups : [
        for env in envs : { eg = eg, env = env }
      ]
    ]) : "${pair.eg}-${pair.env}" => pair
  }

  envgroup_id = google_apigee_envgroup.envgroup[each.value.eg].id
  environment = google_apigee_environment.apigee_env[each.value.env].name
}

resource "google_apigee_instance_attachment" "instance_attachment" {
  for_each    = local.environments
  instance_id = google_apigee_instance.apigee_instance.id
  environment = google_apigee_environment.apigee_env[each.key].name
}

module "ingress_lb" {
  source = "./modules/ingress-lb"

  project_id         = var.gcp_project_id
  name               = "apigee-ingress"
  region             = var.apigee_runtime_location
  domain_name        = local.hostname
  service_attachment = google_apigee_instance.apigee_instance.service_attachment
  network            = google_compute_network.apigee_network.id

  depends_on = [
    google_apigee_organization.apigee_org
  ]
}

# DNS module - only created if hostname is configured
module "dns" {
  count         = local.hostname != null ? 1 : 0
  source        = "./modules/dns"
  dns_zone_name = "apigee-dns"
  hostname      = local.hostname
  lb_ip_address = module.ingress_lb.lb_ip

  depends_on = [
    google_project_service.dns
  ]
}



# --- API Proxy Deployment ---
# API proxies are managed via the CLI, not Terraform.
# Use: ./util apis import <project> --proxy-name <name> --bundle <path>
#      ./util apis deploy <project> --proxy-name <name> --revision <rev> --environment <env>

