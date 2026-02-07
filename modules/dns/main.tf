# DNS A Record for Apigee Environment Group
# This creates a DNS A record pointing to the load balancer IP

variable "dns_zone_name" {
  description = "The name of the Cloud DNS managed zone (must already exist)"
  type        = string
  default     = "apigee-dns"
}

variable "hostname" {
  description = "The full hostname for the A record (e.g., my-project.example.com)"
  type        = string
}

variable "lb_ip_address" {
  description = "The load balancer IP address to point the A record to"
  type        = string
}

resource "google_dns_managed_zone" "apigee_zone" {
  name        = var.dns_zone_name
  dns_name    = "${join(".", slice(split(".", var.hostname), 1, length(split(".", var.hostname))))}."
  description = "Managed zone for Apigee hostnames"
  visibility  = "public"
}

# Create A record
resource "google_dns_record_set" "apigee_a_record" {
  name         = "${var.hostname}."
  managed_zone = google_dns_managed_zone.apigee_zone.name
  type         = "A"
  ttl          = 300
  rrdatas      = [var.lb_ip_address]
}



output "dns_record_name" {
  description = "The DNS record name that was created"
  value       = google_dns_record_set.apigee_a_record.name
}
