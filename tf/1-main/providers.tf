terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
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
  apigee_endpoint = (var.control_plane_location != null && var.control_plane_location != "") ? "https://${var.control_plane_location}-apigee.googleapis.com/v1/" : ""
}

# 2. Default Provider - SA IDENTITY (via env var GOOGLE_IMPERSONATE_SERVICE_ACCOUNT)
# CLI sets this env var to impersonate terraform-deployer
# Used for all other resources
provider "google" {
  project               = var.gcp_project_id
  billing_project       = var.gcp_project_id
  user_project_override = true
  apigee_custom_endpoint = local.apigee_endpoint != "" ? local.apigee_endpoint : null
}

provider "google-beta" {
  project               = var.gcp_project_id
  billing_project       = var.gcp_project_id
  user_project_override = true
  apigee_custom_endpoint = local.apigee_endpoint != "" ? local.apigee_endpoint : null
}
