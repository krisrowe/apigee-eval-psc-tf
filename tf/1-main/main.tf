locals {
  environments = {
    dev = {}
  }
  envgroups = {
    eval-group = ["dev"]
  }

  # Final hostname: Explicit var.domain_name from tfvars (or null for IP-only)
  hostname = var.domain_name
}


# Validation: warn if no hostname is configured
resource "null_resource" "hostname_warning" {
  count = local.hostname == null ? 1 : 0

  provisioner "local-exec" {
    command = "echo 'WARNING: No domain_name configured. Apigee will only be accessible via IP address. Set domain_name in tfvars or configure default_root_domain via: ./util config set default_root_domain example.com'"
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


resource "google_project_service" "iam" {
  project = var.gcp_project_id
  service = "iam.googleapis.com"
}

resource "google_project_service" "secretmanager" {
  project = var.gcp_project_id
  service = "secretmanager.googleapis.com"
}

resource "google_project_service" "crm" {
  project = var.gcp_project_id
  service = "cloudresourcemanager.googleapis.com"
}

resource "google_project_service" "serviceusage" {
  project = var.gcp_project_id
  service = "serviceusage.googleapis.com"
}

resource "google_compute_network" "apigee_network" {
  name                    = "apigee-network"
  project                 = var.gcp_project_id
  auto_create_subnetworks = true
  depends_on              = [google_project_service.compute]
}

# --- APIGEE RESOURCES (Conditional) ---
# If apigee_enabled=false, these are skipped (for fast CI/Network-only testing).

locals {
  # Helper to toggle resource creation
  apigee_count = var.apigee_enabled ? 1 : 0
  
  # Filtered maps for for_each
  active_environments = var.apigee_enabled ? local.environments : {}
  active_envgroups    = var.apigee_enabled ? local.envgroups : {}
}

resource "google_apigee_organization" "apigee_org" {
  count            = local.apigee_count
  project_id       = var.gcp_project_id
  
  # For DRZ: analytics_region must be null (not set), use api_consumer_data_location instead
  analytics_region = (var.consumer_data_region != "" && var.consumer_data_region != null) ? null : var.apigee_analytics_region

  # DRZ only: Set consumer data location
  api_consumer_data_location = (var.consumer_data_region != "" && var.consumer_data_region != null) ? var.consumer_data_region : null

  runtime_type = "CLOUD"

  # Use variable instead of hardcoded PAYG
  billing_type = var.apigee_billing_type

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
  count    = local.apigee_count
  name     = coalesce(var.apigee_instance_name, var.apigee_runtime_location)
  location = var.apigee_runtime_location
  org_id   = google_apigee_organization.apigee_org[0].id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_apigee_environment" "apigee_env" {
  for_each = local.active_environments
  name     = each.key
  org_id   = google_apigee_organization.apigee_org[0].id
  type     = var.apigee_billing_type == "EVALUATION" ? null : "COMPREHENSIVE"
}

resource "google_apigee_envgroup" "envgroup" {
  for_each  = local.active_envgroups
  name      = each.key
  org_id    = google_apigee_organization.apigee_org[0].id
  hostnames = local.hostname != null ? [local.hostname] : []

  lifecycle {
    ignore_changes = [hostnames]
  }
}

resource "google_apigee_envgroup_attachment" "envgroup_attachment" {
  for_each = {
    for pair in flatten([
      for eg, envs in local.active_envgroups : [
        for env in envs : { eg = eg, env = env }
      ]
    ]) : "${pair.eg}-${pair.env}" => pair
  }

  envgroup_id = google_apigee_envgroup.envgroup[each.value.eg].id
  environment = google_apigee_environment.apigee_env[each.value.env].name
}

resource "google_apigee_instance_attachment" "instance_attachment" {
  for_each    = local.active_environments
  instance_id = google_apigee_instance.apigee_instance[0].id
  environment = google_apigee_environment.apigee_env[each.key].name
}

module "ingress_lb" {
  source = "./modules/ingress-lb"
  count  = local.apigee_count

  project_id         = var.gcp_project_id
  name               = "apigee-ingress"
  region             = var.apigee_runtime_location
  domain_name        = local.hostname
  service_attachment = google_apigee_instance.apigee_instance[0].service_attachment
  network            = google_compute_network.apigee_network.id

  depends_on = [
    google_apigee_organization.apigee_org
  ]
}

# DNS module - only created if hostname is configured AND Apigee is enabled
module "dns" {
  count         = (local.hostname != null && var.apigee_enabled) ? 1 : 0
  source        = "./modules/dns"
  dns_zone_name = "apigee-dns"
  hostname      = local.hostname
  lb_ip_address = module.ingress_lb[0].lb_ip

  depends_on = [
    google_project_service.dns
  ]
}



# --- API Proxy Deployment ---
# API proxies are managed via the CLI, not Terraform.
# Use: ./util apis import <project> --proxy-name <name> --bundle <path>
#      ./util apis deploy <project> --proxy-name <name> --revision <rev> --environment <env>

