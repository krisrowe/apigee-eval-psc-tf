output "load_balancer_ip" {
  description = "The public IP address of the external HTTPS Load Balancer."
  value       = google_compute_global_address.northbound_lb_ip.address
}