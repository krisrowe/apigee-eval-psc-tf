terraform {
  required_version = ">= 1.5"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

locals {
  # Construct the DRZ endpoint URL if control_plane_location is set
  apigee_endpoint = var.control_plane_location != "" ? "https://${var.control_plane_location}-apigee.googleapis.com/v1/" : ""
}

provider "google" {
  project = var.gcp_project_id
  
  # Data Residency Zone (DRZ): Use regional control plane if specified
  # When empty, this attribute is omitted and the global endpoint is used
  apigee_custom_endpoint = local.apigee_endpoint != "" ? local.apigee_endpoint : null
}
