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
  default     = "us-central1"
}

variable "apigee_runtime_location" {
  description = "The runtime location (region) for the Apigee instance."
  type        = string
  default     = "us-central1"
}

variable "project_nickname" {
  description = "The nickname for this project, used for labeling and discovery."
  type        = string
}

variable "control_plane_location" {
  description = "The control plane hosting jurisdiction for data residency (e.g., 'ca' for Canada, 'eu' for Europe). Leave empty for global/no DRZ."
  type        = string
  default     = ""
}
