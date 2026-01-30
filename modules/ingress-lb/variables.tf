variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "name" {
  description = "The name for the Load Balancer resources."
  type        = string
}

variable "region" {
  description = "The region for the PSC NEG."
  type        = string
}

variable "domain_name" {
  description = "The domain name for the SSL certificate."
  type        = string
}

variable "service_attachment" {
  description = "The Apigee instance service attachment URI."
  type        = string
}

variable "network" {
  description = "The VPC network for the PSC NEG."
  type        = string
}
