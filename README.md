# Apigee Terraform Provisioning

This repository provides a production-grade Terraform framework for deploying Apigee X/Hybrid organizations on Google Cloud, specifically designed to handle **Evaluation Logic**, **Data Residency (DRZ)**, and **Private Service Connect (PSC)** ingress.

It interacts seamlessly with a custom CLI utility (`./util`) to manage multiple project configurations without polluting the repository.

## Capabilities

-   **Modular Design**: Resources are flattened for simplicity but logically separated (Core vs. Ingress).
-   **Data Residency (DRZ)**: Supports creating Organization in specific Control Plane jurisdictions (e.g., Canada `northamerica-northeast1`).
-   **Billing Awareness**: Automatically handles `PAYG` (Pay-as-you-go) vs. `EVALUATION` billing types based on project constraints and DRZ requirements.
-   **State Management**: Stores state locally in `~/.local/share/apigee-tf/`, keeping your git repository clean.
-   **Discovery**: Can "Import" existing cloud resources into Terraform state automatically.

---

## Prerequisites

Before you begin, ensure you have:

1.  **Google Cloud Project**:
    -   Must have **Billing Enabled** (Required for DRZ/PAYG).
    -   Must have `Owner` or `Editor` permissions.
2.  **Tools**:
    -   `gcloud` CLI (Authenticated: `gcloud auth application-default login`)
    -   Terraform (v1.5+)
    -   Python 3

---

## Quick Start Scenarios

Choose the scenario that matches your situation.

### Scenario 1: Brand New Project (Clean Slate)
*Use this if you have a freshly created Project ID and want to provision Apigee from scratch, possibly with DRZ.*

1.  **Prepare Project**:
    Ensure your project exists and has billing linked.
    ```bash
    gcloud projects create my-new-project-id
    gcloud beta billing projects link my-new-project-id --billing-account=YOUR_BILLING_ACCT_ID
    ```

2.  **Initialize Config**:
    Use the `import` command to create a local configuration profile. Use `--force` since the project is empty.
    ```bash
    ./util import my-alias --project my-new-project-id --force
    ```
    *This creates `~/.config/apigee-tf/projects/my-alias.tfvars` aligned to the project.*

3.  **Configure DRZ (Optional)**:
    If you need Data Residency (e.g., Canada), edit your tfvars file:
    ```bash
    # Edit ~/.config/apigee-tf/projects/my-alias.tfvars
    control_plane_location = "ca"  # or "eu", "au" etc.
    apigee_analytics_region = "northamerica-northeast1"
    apigee_runtime_location = "northamerica-northeast1"
    ```

4.  **Deploy**:
    ```bash
    ./util apply my-alias
    ```
    *Note: Organization creation takes ~20-30 minutes.*

### Scenario 2: Existing Project (Discovery)
*Use this if you already have an Apigee Organization and want to bring it under Terraform management.*

1.  **Import & Align**:
    Run `import` without force. The tool will probe the API for existing Org, Instances, and Environment Groups.
    ```bash
    ./util import existing-alias --project existing-project-id
    ```
    
2.  **Generate Import Blocks**:
    The tool generates `generated_imports.tf`. Review this file to see what resources will be imported into Terraform state.

3.  **Plan & Apply**:
    ```bash
    ./util plan existing-alias
    ./util apply existing-alias
    ```
    *Terraform will sync its state with the cloud resources without destroying them.*

---

## Configuration Reference

The behavior of the deployment is controlled by `~/.config/apigee-tf/projects/<alias>.tfvars`.

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `gcp_project_id` | **Required.** Target GCP Project ID. | `my-project-id` |
| `project_nickname` | **Required.** Config alias name. | `my-alias` |
| `apigee_analytics_region` | Primary region for Analytics/Data. | `northamerica-northeast1` |
| `apigee_runtime_location` | Region for Runtime Instance. | `northamerica-northeast1` |
| `control_plane_location` | **Critical for DRZ.** Control plane jurisdiction. Leave empty for Global. | `"ca"` (Canada), `"eu"` (Europe), `""` (Global) |
| `domain_name` | Domain for SSL/DNS. | `my-alias.example.com` |

---

## Architecture & Billing Types

### Billing: PAYG vs. Evaluation
-   **PAYG (Pay-as-you-go)**: Hardcoded default for this repo. Required for DRZ. Requires a valid billing account linked to the project.
-   **EVALUATION**: Standard free tier. **Does not support DRZ** (Control Plane Data Residency).

### Network Topology
Traffic enters via **Global External Load Balancer (GXLB)** -> **Private Service Connect (PSC)** -> **Apigee Runtime**.
This architecture is secure, private, and does not require VPC Peering peering limits.

---

## Common Issues

### "Billing type EVALUATION is not allowed"
**Cause**: You requested DRZ (`control_plane_location="ca"`) but the API rejected the request, usually because the project lacks a valid Billing Account link or entitlements.
**Fix**:
1.  Verify Billing is linked: `gcloud beta billing projects describe PROJECT_ID`
2.  Ensure you have `apigee.googleapis.com` enabled.
3.  Use a Fresh Project. Legacy projects with expired evaluations can get stuck.

### "Resource already exists"
**Cause**: You tried to `apply` on a project that already has Apigee, but your State file is empty.
**Fix**: Use `Scenario 2` (Import) to recover state.

---

## CLI Utility (`./util`)

Wrapper around Terraform to manage multi-project state/config.

-   `./util list` - List configured projects.
-   `./util import <alias>` - Discovery & Setup.
-   `./util plan <alias>` - Dry run.
-   `./util apply <alias>` - Deploy.