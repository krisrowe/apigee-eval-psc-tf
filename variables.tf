variable "gcp_project_id" {
  description = "The GCP project ID where Apigee will be provisioned."
  type        = string
}

variable "domain_name" {
  description = "The domain name for the Apigee Ingress Load Balancer."
  type        = string
}

variable "apigee_analytics_region" {
  description = "The analytics region for the Apigee organization."
  type        = string
  default     = "us-central1" # Or your desired default region
}

variable "apigee_runtime_location" {
  description = "The runtime location (region) for the Apigee instance."
  type        = string
  default     = "us-central1" # Or your desired default region
}
