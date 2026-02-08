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

# --- ADMIN GROUP (SECURITY BEST PRACTICE) ---
# We avoid assigning roles directly to the Service Account.
# Instead, we create a Google Group, assign roles to the Group, and make the SA a member.
# This allows for:
# 1. Auditability: Single place to see who has admin access (the group members).
# 2. Stacking: We can add human admins to this group for emergency access without changing IAM bindings.
resource "google_cloud_identity_group" "apigee_admins" {
  display_name = "Apigee Admins"
  description  = "Members of this group have Apigee administrative privileges."
  parent       = "customers/${local.org_customer_id}"
  
  group_key {
    id = "apigee-admins@${local.org_domain}"
  }
  
  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }
  
  depends_on = [google_project_service.cloudidentity]
}

# Add the terraform-deployer SA to the group
# This ensures the SA inherits the permissions granted to the group.
resource "google_cloud_identity_group_membership" "deployer_in_admins" {
  group    = google_cloud_identity_group.apigee_admins.id
  
  preferred_member_key {
    id = google_service_account.deployer.email
  }
  
  roles {
    name = "MEMBER"
  }
}

# Grant Owner to the GROUP (not the SA directly)
# The Service Account becomes an Owner ONLY because it is a member of this group.
resource "google_project_iam_member" "admin_group_owner" {
  project    = var.gcp_project_id
  role       = "roles/owner"
  member     = "group:apigee-admins@${local.org_domain}"
  depends_on = [google_cloud_identity_group.apigee_admins]
}

# --- DENY POLICY ---
# When allow_deletes=false (default), this policy BLOCKS the group from deleting protected resources
# Uses bootstrap provider because only user should manage deny policies
resource "google_iam_deny_policy" "protect_deletes" {
  count    = var.allow_deletes ? 0 : 1
  provider = google-beta
  name     = "protect-deletes"
  parent   = "cloudresourcemanager.googleapis.com%2Fprojects%2F${var.gcp_project_id}"
  
  # depends_on = [google_project_service.crm] # Removed as API enablement is assumed/handled
  
  rules {
    deny_rule {
      denied_principals = ["group:apigee-admins@${local.org_domain}"]
      denied_permissions = [
        "secretmanager.secrets.delete",
        "apigee.instances.delete",
        "apigee.organizations.delete"
      ]
    }
  }
}
