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

# --- PROJECT ACCESS ---
# Grant roles directly to the Service Account.
# We grant Editor for general resource management, and IAM Admin roles 
# to allow the SA to manage runtime identities and service permissions in Phase 1.
resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/editor",                         # General resource management (cannot modify IAM policies)
    "roles/resourcemanager.projectIamAdmin", # Allows Terraform to grant project-level roles (e.g. roles/aiplatform.user, roles/modelarmor.viewer) to the runtime service account
    "roles/iam.serviceAccountAdmin"         # Allows Terraform to grant the Apigee Service Agent permission to impersonate the runtime service account (via roles/iam.serviceAccountUser)
  ])
  project = var.gcp_project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# --- DENY POLICY ---
# We still create the Deny Policy to protect secrets, targeting the global Admin Group.
# This assumes the group exists, but we don't manage its membership here.
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
