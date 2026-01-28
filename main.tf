terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.54.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.2.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
}

# --- GCP Project Services ---

resource "google_project_service" "apigee" {
  service = "apigee.googleapis.com"
}

resource "google_project_service" "cloudkms" {
  service = "cloudkms.googleapis.com"
}

resource "google_project_service" "compute" {
  service = "compute.googleapis.com"
}

resource "google_project_service" "servicenetworking" {
  service = "servicenetworking.googleapis.com"
}

# --- Apigee Core Components ---

resource "google_apigee_organization" "apigee_org" {
  project_id          = var.gcp_project_id
  display_name        = var.gcp_project_id # Using project ID as display name
  description         = "Apigee organization for evaluation"
  analytics_region    = var.apigee_analytics_region
  runtime_type        = "CLOUD"
  billing_type        = "EVALUATION"
  disable_vpc_peering = true

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
}

# --- Apigee API Proxy Deployment ---

data "archive_file" "weather_api_bundle" {
  type        = "zip"
  source_dir  = "apiproxies/weather-api"
  output_path = "${path.module}/weather-api.zip"
}

resource "google_apigee_api" "weather_api" {
  org_id        = google_apigee_organization.apigee_org.id
  name          = "weather-api"
  config_bundle = data.archive_file.weather_api_bundle.output_path
}

resource "google_apigee_api_deployment" "weather_api_deployment" {
  org_id      = google_apigee_api.weather_api.org_id
  environment = "eval"
  proxy_id    = google_apigee_api.weather_api.name
  revision    = google_apigee_api.weather_api.latest_revision_id

  depends_on = [
    google_apigee_instance.apigee_instance
  ]
}

# --- Ingress Layer (External HTTPS Load Balancer) ---

resource "google_compute_global_address" "northbound_lb_ip" {
  name = "apigee-eval-psc-ip"
}

resource "google_compute_managed_ssl_certificate" "northbound_lb_ssl_cert" {
  name = "apigee-ingress-cert"
  managed {
    domains = [var.domain_name]
  }
}

resource "google_compute_health_check" "northbound_lb_health_check" {
  name                = "apigee-proxy-health-check"
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 2

  tcp_health_check {
    port = "443"
  }
}

resource "google_compute_region_network_endpoint_group" "northbound_psc_neg" {
  name                  = "apigee-psc-neg"
  network_endpoint_type = "PRIVATE_SERVICE_CONNECT"
  psc_target_service    = google_apigee_instance.apigee_instance.service_attachment
  region                = var.apigee_runtime_location
  
  depends_on = [google_apigee_instance.apigee_instance]
}

resource "google_compute_backend_service" "northbound_lb_backend_service" {
  name                  = "apigee-psc-backend"
  protocol              = "HTTPS"
  port_name             = "https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  health_checks         = [google_compute_health_check.northbound_lb_health_check.id]

  backend {
    group = google_compute_region_network_endpoint_group.northbound_psc_neg.id
  }
}

resource "google_compute_url_map" "northbound_lb_url_map" {
  name            = "apigee-proxy-url-map"
  default_service = google_compute_backend_service.northbound_lb_backend_service.id
}

resource "google_compute_target_https_proxy" "northbound_lb_https_proxy" {
  name             = "apigee-proxy-https-proxy"
  url_map          = google_compute_url_map.northbound_lb_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.northbound_lb_ssl_cert.id]
}

resource "google_compute_global_forwarding_rule" "northbound_lb_forwarding_rule" {
  name       = "apigee-proxy-forwarding-rule"
  target     = google_compute_target_https_proxy.northbound_lb_https_proxy.id
  ip_address = google_compute_global_address.northbound_lb_ip.address
  port_range = "443"
}