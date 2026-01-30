locals {
  environments = {
    eval = {}
  }
  envgroups = {
    eval-group = ["eval"]
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

resource "google_apigee_organization" "apigee_org" {
  project_id                 = var.gcp_project_id
  analytics_region           = var.apigee_analytics_region
  
  # Dynamic Data Location Logic
  api_consumer_data_location = var.control_plane_location != null && var.control_plane_location != "" ? var.apigee_analytics_region : null
  
  runtime_type               = "CLOUD"
  
  # HARDCODED AS REQUESTED
  billing_type               = "PAYG" 
  
  disable_vpc_peering        = true

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    google_project_service.apigee,
    google_project_service.cloudkms,
    google_project_service.compute,
    google_project_service.servicenetworking,
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
}

resource "google_apigee_envgroup" "envgroup" {
  for_each = local.envgroups
  name      = each.key
  org_id    = google_apigee_organization.apigee_org.id
  hostnames = ["*"] 
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
  domain_name        = var.domain_name
  service_attachment = google_apigee_instance.apigee_instance.service_attachment

  depends_on = [
    google_apigee_organization.apigee_org
  ]
}

# --- Apigee API Proxy Deployment (Example) ---
# NOTE: These resources are not yet available in the stable google provider

# data "archive_file" "weather_api_bundle" {
#   type        = "zip"
#   source_dir  = "apiproxies/weather-api"
#   output_path = "${path.module}/weather-api.zip"
# }

# resource "google_apigee_api" "weather_api" {
#   org_id        = module.apigee_core.org_id
#   name          = "weather-api"
#   config_bundle = data.archive_file.weather_api_bundle.output_path
# }

# resource "google_apigee_api_deployment" "weather_api_deployment" {
#   org_id      = module.apigee_core.org_id
#   environment = "eval"
#   proxy_id    = google_apigee_api.weather_api.name
#   revision    = google_apigee_api.weather_api.latest_revision_id

#   depends_on = [
#     module.apigee_core
#   ]
# }