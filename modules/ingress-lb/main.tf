resource "google_compute_global_address" "lb_ip" {
  project = var.project_id
  name    = "${var.name}-ip"
}

resource "google_compute_managed_ssl_certificate" "lb_cert" {
  count   = var.domain_name != null ? 1 : 0
  project = var.project_id
  name    = "${var.name}-cert-${substr(md5(var.domain_name), 0, 8)}"
  managed {
    domains = [var.domain_name]
  }
  lifecycle {
    create_before_destroy = true
  }
}


resource "google_compute_health_check" "lb_health_check" {
  project = var.project_id
  name    = "${var.name}-health-check"
  check_interval_sec  = 5
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 2

  tcp_health_check {
    port = "443"
  }
}

resource "google_compute_region_network_endpoint_group" "psc_neg" {
  project               = var.project_id
  name                  = "${var.name}-psc-neg"
  network_endpoint_type = "PRIVATE_SERVICE_CONNECT"
  psc_target_service    = var.service_attachment
  region                = var.region
  network               = var.network

  lifecycle {
    ignore_changes = [subnetwork]
  }
}


resource "google_compute_backend_service" "lb_backend" {
  project               = var.project_id
  name                  = "${var.name}-backend"
  protocol              = "HTTPS"
  port_name             = "https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  # Health checks are not supported for PSC NEG backends
  # health_checks         = [google_compute_health_check.lb_health_check.id]

  backend {
    group = google_compute_region_network_endpoint_group.psc_neg.id
  }
}

resource "google_compute_url_map" "lb_url_map" {
  project         = var.project_id
  name            = "${var.name}-url-map"
  default_service = google_compute_backend_service.lb_backend.id
}

resource "google_compute_target_https_proxy" "lb_proxy" {
  count            = var.domain_name != null ? 1 : 0
  project          = var.project_id
  name             = "${var.name}-https-proxy"
  url_map          = google_compute_url_map.lb_url_map.id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb_cert[0].id]
}

resource "google_compute_global_forwarding_rule" "lb_forwarding_rule" {
  count                 = var.domain_name != null ? 1 : 0
  project               = var.project_id
  name                  = "${var.name}-forwarding-rule"
  target                = google_compute_target_https_proxy.lb_proxy[0].id
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
