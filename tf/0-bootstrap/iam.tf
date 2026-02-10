# --- ORGANIZATION & CUSTOMER ID LOOKUP ---
# These run with bootstrap (user) identity
data "google_project" "current" {
  project_id = var.gcp_project_id
}

data "google_organization" "current" {
  organization = data.google_project.current.org_id
}

locals {
  org_customer_id = data.google_organization.current.directory_customer_id
  org_domain      = data.google_organization.current.domain
}

# --- CLOUD IDENTITY API ---
resource "google_project_service" "cloudidentity" {
  project            = var.gcp_project_id
  service            = "cloudidentity.googleapis.com"
  disable_on_destroy = false
}

# --- SERVICE ACCOUNT ---
# Created with bootstrap (user) identity
resource "google_service_account" "deployer" {
  account_id   = "terraform-deployer"
  display_name = "Terraform Deployer Service Account"
}

# --- IMPERSONATION ACCESS ---
# Explicitly grant the creating user the ability to impersonate this SA.
# This propagates faster than Project Owner inheritance.
resource "google_service_account_iam_member" "token_creator" {
  count              = var.current_user_email != null ? 1 : 0
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.current_user_email}"
}

# --- ADMIN GROUP (SECURITY BEST PRACTICE) ---
# We treat the Admin Group as a Global Singleton. 
# It is assumed to exist at the Organization level.
data "google_cloud_identity_group_lookup" "apigee_admins" {
  group_key {
    id = "apigee-admins@${local.org_domain}"
  }
}

# Add the terraform-deployer SA to the group
resource "google_cloud_identity_group_membership" "deployer_in_admins" {
  group    = data.google_cloud_identity_group_lookup.apigee_admins.name
  
  preferred_member_key {
    id = google_service_account.deployer.email
  }
  
  roles {
    name = "MEMBER"
  }
}

# Grant Owner to the GROUP (not the SA directly)
resource "google_project_iam_member" "admin_group_owner" {
  project    = var.gcp_project_id
  role       = "roles/owner"
  member     = "group:apigee-admins@${local.org_domain}"
}

# --- DENY POLICY ---
# When allow_deletes=false (default), this policy BLOCKS the group from deleting protected resources
# Uses bootstrap provider because only user should manage deny policies
resource "google_iam_deny_policy" "protect_deletes" {
  count    = var.allow_deletes ? 0 : 1
  provider = google-beta
  name     = "protect-deletes"
  parent   = "cloudresourcemanager.googleapis.com%2Fprojects%2F${var.gcp_project_id}"
  
  rules {
    deny_rule {
      denied_principals = ["principalSet://goog/group/apigee-admins@${local.org_domain}"]
      denied_permissions = [
        "secretmanager.googleapis.com/secrets.delete"
      ]
    }
  }
}
