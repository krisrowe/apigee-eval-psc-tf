output "org_id" {
  value = google_apigee_organization.apigee_org.id
}

output "instance_id" {
  value = google_apigee_instance.apigee_instance.id
}

output "service_attachment" {
  value = google_apigee_instance.apigee_instance.service_attachment
}
