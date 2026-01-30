output "apigee_lb_ip" {
  description = "The public IP address of the Apigee Ingress Load Balancer."
  value       = module.ingress_lb.lb_ip
}

output "apigee_org_id" {
  description = "The ID of the created Apigee Organization."
  value       = google_apigee_organization.apigee_org.id
}