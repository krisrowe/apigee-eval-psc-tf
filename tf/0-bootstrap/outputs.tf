output "service_account_email" {
  description = "The email of the provisioning Service Account."
  value       = google_service_account.deployer.email
}
