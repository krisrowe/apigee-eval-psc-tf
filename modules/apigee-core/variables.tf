variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "ax_region" {
  description = "The analytics region for the Apigee organization."
  type        = string
}

variable "runtime_location" {
  description = "The runtime location (region) for the Apigee instance."
  type        = string
}

variable "project_nickname" {
  description = "The nickname for this project, used for labeling."
  type        = string
}

variable "billing_type" {
  description = "Billing type of the Apigee organization (EVALUATION or SUBSCRIPTION)."
  type        = string
  default     = "EVALUATION"
}

variable "api_consumer_data_location" {
  description = "Location for consumer data (DRZ). Leave null for global."
  type        = string
  default     = null
}

variable "environments" {
  description = "Map of Apigee environments to create."
  type        = map(any)
  default     = {
    eval = {}
  }
}

variable "envgroups" {
  description = "Map of Apigee environment groups to create."
  type        = map(list(string))
  default     = {
    eval-group = ["eval"]
  }
}
