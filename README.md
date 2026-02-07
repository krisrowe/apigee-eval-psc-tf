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
    
    # Optional: Get Billing ID from an existing project
    BILLING_ID=$(gcloud beta billing projects describe OTHER_PROJECT_ID --format="value(billingAccountName.segment(-1))")
    gcloud beta billing projects link my-new-project-id --billing-account=$BILLING_ID
    ```

2.  **Initialize Config**:
    Setup your project configuration profile using the `import` command.
    
    *Variation A: Explicit Project ID*
    ```bash
    ./util import my-alias --project my-new-project-id --template templates/ca-drz.json
    ```

    *Variation B: Auto-Discovery (uses project labels)*
    ```bash
    ./util import my-alias --template templates/ca-drz.json
    ```

3.  **Verify Configuration**:
    Run the show command to verify the configuration before deploying.
    ```bash
    ./util show my-alias
    ```
    *Manual Verification: Inspect the raw file at `$HOME/.config/apigee-tf/projects/my-alias.tfvars` or run `./util show my-alias --raw`*

4.  **Deploy**:
    ```bash
    ./util apply my-alias
    ```
    *Manual Execution: This wraps `terraform apply -var-file=$HOME/.config/apigee-tf/projects/my-alias.tfvars`*

    *Note: Organization and Instance creation takes ~20-30 minutes.*

> [!TIP]
> **Custom Inputs**: To provide your own configuration (e.g. custom domain) without editing files, create a JSON template:
> ```json
> {
>   "domain_name": "api.custom.com",
>   "apigee_analytics_region": "us-central1"
> }
> ```
> Then pass it: `./util import my-alias --project my-id --template my-config.json`

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
    ./util show existing-alias
    ```
    *Manual execution: Direct terraform commands are available once the workspace is selected.*

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
**Cause**: You requested DRZ (`control_plane_location="ca"`) but the GCP API rejected the request. Usually, this means the project is in a **corrupted/expired evaluation state** where legacy settings prevent paid provisioning, even after linking a billing account.
**Fix**: 
1.  Verify Billing is linked: `gcloud beta billing projects describe PROJECT_ID`
2.  **Move to a Fresh Project**. For DRZ, the safest path is initializing a brand new Google Cloud Project and linking billing *before* enabling Apigee.

### "Resource already exists"
**Cause**: You tried to `apply` on a project that already has Apigee, but your State file is empty.
**Fix**: Use `Scenario 2` (Import) to recover state.

---

## CLI Utility (`./util`)

Wrapper around Terraform and GCP APIs to manage multi-project state/config.

### Configuration
-   `./util config show` - Show all available settings with descriptions.
-   `./util config set <key> <value>` - Set a global CLI setting (e.g., `default_root_domain`).
-   `./util config get` - View current global settings.

### Infrastructure
-   `./util import <alias> --project <id>` - Setup or Import project configuration.
-   `./util init <alias>` - Initialize Terraform backend.
-   `./util plan/apply <alias>` - Manage core infrastructure.
-   `./util show <alias>` - **Total Status!** Shows local config, live Apigee resources (Org/Instance), and Ingress readiness (DNS/SSL status).

### API Management
-   `./util apis list <alias>` - List API proxies.
-   `./util apis import <alias> --proxy-name <name> --bundle <path>` - Import a proxy bundle.
-   `./util apis deploy <alias> --proxy-name <name> --revision <rev>` - Deploy to an environment.
-   `./util apis test <alias> --proxy-name <name> --bundle <path>` - **New!** Run integration tests with automatic infrastructure readiness checks.

---

## Hostname Fallback Logic

The system uses a three-tier fallback for environment group hostnames:
1.  **Tier 1 (Explicit)**: `domain_name` in `$HOME/.config/apigee-tf/projects/<alias>.tfvars`.
2.  **Tier 2 (Auto-derived)**: `{project_nickname}.{default_root_domain}` (from global config).
3.  **Tier 3 (IP-only)**: Fallback to IP with a warning if no domain is configured.

---

## Appendix A: Custom Domain Setup & Validation

To use a custom domain (e.g., `example.com`) with this tool, follow these steps to ensure proper delegation and automation:

### 1. Configure Global Root
Set your parent domain as the default root. This enables the CLI to auto-derive hostnames for new projects (e.g., `my-project.example.com`).
```bash
./util config set default_root_domain example.com
```

### 2. Identify GCP Name Servers
Once you run `./util apply` for a project, Terraform creates a Managed Zone. You must find the specific name servers Google assigned to that zone:
```bash
gcloud dns managed-zones describe apigee-dns --project <gcp-project-id> --format="value(nameServers)"
```
*Note: Google uses clusters (a, b, c, d). Your project might be assigned `ns-cloud-d1...` while another uses `ns-cloud-a1...`.*

### 3. Update Registrar
Log into your domain registrar (Squarespace, etc.) and update the **Custom Name Servers** for your domain to match the 4 addresses found in Step 2.

### 4. Validate Delegation
Verify that the internet sees your new name servers. A mismatch here will cause `NXDOMAIN` errors.
```bash
dig NS yourdomain.com +short
```

### 5. Verify Resolution
Check if your specific Apigee hostname is resolving to the Load Balancer IP by querying the assigned servers directly:
```bash
dig @ns-cloud-d1.googledomains.com my-project.yourdomain.com +short
```

Use `./util show <alias>` to monitor the live status of DNS propagation and SSL provisioning.