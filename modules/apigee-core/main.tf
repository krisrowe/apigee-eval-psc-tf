resource "null_resource" "project_label" {
  provisioner "local-exec" {
    command = "gcloud projects update ${var.project_id} --update-labels=apigee-tf=${var.project_nickname}"
  }
}

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_project_service" "apigee" {
  project = var.project_id
  service = "apigee.googleapis.com"
}

resource "google_project_service" "cloudkms" {
  project = var.project_id
  service = "cloudkms.googleapis.com"
}

resource "google_project_service" "compute" {
  project = var.project_id
  service = "compute.googleapis.com"
}

resource "google_project_service" "servicenetworking" {
  project = var.project_id
  service = "servicenetworking.googleapis.com"
}

resource "google_apigee_organization" "apigee_org" {
  project_id               = var.project_id
  analytics_region           = var.ax_region
  api_consumer_data_location = var.api_consumer_data_location
  runtime_type               = "CLOUD"
  billing_type               = var.billing_type
  disable_vpc_peering      = true

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
  name     = var.runtime_location
  location = var.runtime_location
  org_id   = google_apigee_organization.apigee_org.id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_apigee_environment" "apigee_env" {
  for_each = var.environments
  name     = each.key
  org_id   = google_apigee_organization.apigee_org.id
}

resource "google_apigee_envgroup" "envgroup" {
  for_each = var.envgroups
  name      = each.key
  org_id    = google_apigee_organization.apigee_org.id
  hostnames = ["*"] # Will be refined by the LB
}

resource "google_apigee_envgroup_attachment" "envgroup_attachment" {
  for_each = {
    for pair in flatten([
      for eg, envs in var.envgroups : [
        for env in envs : { eg = eg, env = env }
      ]
    ]) : "${pair.eg}-${pair.env}" => pair
  }

  envgroup_id = google_apigee_envgroup.envgroup[each.value.eg].id
  environment = google_apigee_environment.apigee_env[each.value.env].name
}

resource "google_apigee_instance_attachment" "instance_attachment" {
  # For evaluation, we attach all environments to the single instance
  for_each    = var.environments
  instance_id = google_apigee_instance.apigee_instance.id
  environment = google_apigee_environment.apigee_env[each.key].name
}
