output "apigee_lb_ip" {
  description = "The public IP address of the Apigee Ingress Load Balancer (or null if skipped)."
  value       = one(module.ingress_lb[*].lb_ip)
}

output "apigee_org_id" {
  description = "The ID of the created Apigee Organization (or null if skipped)."
  value       = one(google_apigee_organization.apigee_org[*].id)
}

output "envgroup_hostname" {
  description = "The hostname configured for the environment group."
  value       = local.hostname
}