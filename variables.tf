variable "gcp_project_id" {
  description = "The GCP project ID where Apigee will be provisioned."
  type        = string
}

variable "domain_name" {
  description = "The domain name for the Apigee Ingress Load Balancer."
  type        = string
  default     = null
}

variable "default_root_domain" {
  description = "The default root domain for auto-deriving hostnames."
  type        = string
  default     = null
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

variable "apigee_instance_name" {
  description = "The name of the Apigee instance."
  type        = string
  default     = null
}

variable "project_nickname" {
  description = "The nickname for this project."
  type        = string
  default     = null
}

variable "control_plane_location" {
  description = "The control plane hosting jurisdiction for data residency."
  type        = string
  default     = ""
}

variable "consumer_data_region" {
  description = "The consumer data region for DRZ."
  type        = string
  default     = ""
}

variable "apigee_billing_type" {
  description = "The billing type for the Apigee organization."
  type        = string
  default     = "EVALUATION"
}

variable "deployer_principal" {
  description = "The principal allowed to impersonate the terraform-deployer."
  type        = string
  default     = null
}

variable "admin_group_email" {
  description = "The email of the Google Group for Apigee Admins."
  type        = string
  default     = null
}

# --- IDENTITY & DENY-DELETES TEST VARIABLES ---

variable "skip_impersonation" {
  description = "When true, use ADC directly. When false (default), ADC impersonates terraform-deployer SA."
  type        = bool
  default     = false
}

variable "allow_deletes" {
  description = "When true, removes the deny policy allowing deletes. Default false = protected."
  type        = bool
  default     = false
}

variable "fake_secret" {
  description = "When true, creates a test secret for deny-deletes verification."
  type        = bool
  default     = false
}
