# IAM & Security Architecture

This document outlines the Identity and Access Management (IAM) strategy, the "Clean Default" impersonation pattern, and the multi-phase bootstrap process required to provision Apigee X on Google Cloud securely.

## Core Philosophy: "Groups Only" & "Clean Defaults"

To adhere to strict enterprise security standards (e.g., banking/governance requirements), we follow these principles:

1.  **No Direct User Assignment**: Humans should never be directly assigned IAM roles on resources.
    - **Instead**: Assign roles to **Google Groups**. Add humans to those groups.
    - **Benefit**: Auditability, centralized membership management, and easy offboarding.

2.  **No Direct Service Account Assignment**: Service Accounts should ideally be members of groups too.
    - **Our Implementation**: We strictly follow this. The `terraform-deployer` Service Account has **ZERO direct IAM roles** on the project. It is simply a member of the `apigee-admins` group, and that group holds the roles.

3.  **Least Privilege via Impersonation**:
    - The CI/CD pipeline (or your local CLI) should NOT run as "Owner".
    - It should authenticate as a high-privilege user (or AD identity) and **impersonate** a specific, scoped Service Account (`terraform-deployer`) for the actual provisioning.
    - This establishes a "Break Glass" mechanism where the impersonation can be blocked (via Deny Policy) without revoking the user's underlying access.

## The "Chicken-and-Egg" Problem

Provisioning a fresh Google Cloud Project presents a circular dependency dilemma:

1.  **Terraform Needs an Identity**: To create resources, Terraform needs a Service Account (SA) to impersonate.
2.  **Identity Needs APIs**: To create the SA, the `iam.googleapis.com` API must be enabled.
3.  **APIs Need Enablement**: To enable the API, you need a purely "User" identity (ADC) and a valid Billing/Quota configuration.
4.  **Billing Needs Access**: To link billing, you need permissions often guarded by the very APIs you haven't enabled yet.

## The Solution: 3-Layer Bootstrap

We resolve this by splitting the provisioning lifecycle into three distinct layers. This is handled automatically by the `apim` CLI (`apim apply --bootstrap`).

### Layer 1: API Enablement (User Identity + Quota Project)
*   **Identity**: Your User Credentials (ADC) directly.
*   **Billing/Quota**: Uses your **Quota Project** (set via `gcloud auth application-default set-quota-project`) to pay for the API enablement calls.
*   **Action**: Enables `cloudresourcemanager`, `serviceusage`, `iam`, `cloudidentity`.
*   **Why?**: You cannot create a Service Account if the IAM API is disabled.

### Layer 2: Identity Creation (User Identity + Target Project)
*   **Identity**: Your User Credentials (ADC) directly.
*   **Billing/Quota**: Now uses the **Target Project** (since APIs are enabled).
*   **Action**:
    1.  Creates the `terraform-deployer` Service Account.
    2.  Creates Google Groups (e.g., `gcp-apigee-admins`) via Cloud Identity (optional/if configured).
    3.  Assigns IAM Roles (`roles/owner`, `roles/resourcemanager.projectIamAdmin`) to the **Service Account** and **Groups**.
    4.  Creates `google_service_account_iam_member` to allow YOU (the user) to impersonate the SA.
*   **Why?**: You cannot verify Impersonation in Layer 3 if the SA and its permissions don't exist.

### Layer 3: Infrastructure Provisioning (Impersonated SA)
*   **Identity**: The **Impersonated Service Account** (`terraform-deployer`).
*   **Action**: Provisions the actual Apigee Organization, Instances, Environment Groups, and Attachments.
*   **Why?**: This ensures that the long-running state file is owned and managed by a stable, non-human identity. It also proves that the SA has sufficient permissions to manage the lifecycle.

## Implementation Details

### Terraform Configuration (`iam.tf`)
The `iam.tf` file (configured with `alias = "bootstrap"`) manages Layer 1 and 2 resources. It uses the `google.bootstrap` provider which:
1.  Skips Impersonation (`access_token` is null or user-derived).
2.  Can fallback to ADC Quota Project for API calls.

### Terraform Configuration (`main.tf` / Default Provider)
The default provider is configured to **automatically impersonate** the Service Account created in Layer 2:
```hcl
provider "google" {
  access_token = data.google_service_account_access_token.default.access_token
}
```
This is the "Clean Default" pattern: 99% of your resources don't need `provider = google.impersonated` tags; they just use the default provider, which IS the impersonated identity.

## Security Controls: Deny Policies

To enforce the usage of the Service Account (and prevent "Shadow IT" by Owners), we can apply a **Deny Policy**:
- **Deny Action**: `secretmanager.secrets.delete` (example).
- **Target**: All Principals (Groups, Users).
- **Exception**: `serviceAccount:terraform-deployer@...`.

This ensures that even Project Owners cannot accidentally delete critical resources, while the automation (Terraform) retains the ability to manage the full lifecycle.
