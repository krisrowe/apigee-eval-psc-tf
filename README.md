# Apigee Terraform Provisioning

This repository provides a production-grade Terraform framework for deploying Apigee X/Hybrid on Google Cloud. It is specifically designed for repeatable, consultant-ready deployments involving **Evaluation Logic**, **Data Residency (DRZ)**, and **Private Service Connect (PSC)** ingress.

It interacts with a lightweight CLI utility (`apim`) to manage configurations and local state without polluting your git repositories.

## Key Features

-   **Zero-Boilerplate Billing**: Automatically defaults to `EVALUATION` but auto-upgrades to `PAYG` if Data Residency is required.
-   **Smart State Management**: Automatically isolates Terraform state files in `~/.local/share/apigee-tf/` using the **GCP Project ID** as a unique key. No state collisions, ever.
-   **Clean Repo Workflow**: Keeps your configuration (`apigee.tfvars`) in your local workspace while keeping the "mechanical" Terraform files and states outside of it.
-   **Discovery & Testing**: Includes built-in tools to import existing cloud resources and run automated integration tests.

---

## Prerequisites

1.  **Google Cloud Project** with **Billing Enabled**.
2.  **Authentication**: `gcloud auth application-default login`
3.  **Local Tools**: Terraform (v1.5+), Python 3.
4.  **Quota Project**: You MUST set a valid quota project for ADC to enable APIs on new projects:
    ```bash
    gcloud auth application-default set-quota-project <your-billing-enabled-project-id>
    ```


---

## Installation

The most reliable way to install the CLI utility is via `make install`, which uses `pipx` to isolate dependencies and register the `apim` command globally.

```bash
make install
```

---

## Configuration

**Strict Policy:**
*   **Filename:** `terraform.tfvars` (ONLY). `apigee.tfvars` is **forbidden**.
*   **Content:** Minimal. Primarily `gcp_project_id`.
*   **Location:** In your project's working directory (e.g. `~/ws/my-client/my-project/`). **NEVER** inside the `apigee-tf` repository itself.

**Example `terraform.tfvars`:**
```hcl
gcp_project_id = "my-project-id"
# Optional overrides only if defaults (us-central1) don't apply
# apigee_runtime_location = "us-east1"
```

## Workflows

### 1. New Project (Greenfield)
Initialize and deploy a new Apigee Organization using a strict template.

1.  **Create**:
    Run `create` with your Project ID and a template (e.g., `ca-drz` or `us-central1`).
    ```bash
    # Uses packaged template 'ca-drz' (config/ca-drz.json)
    apim create my-project-id ca-drz
    ```
    *This generates `terraform.tfvars` and deploys the infrastructure via Terraform.*

2.  **Verify**:
    The command will output the dashboard URL and status upon success.

### 2. Ongoing Maintenance (Day 2+)
Update an existing deployment after modifying `terraform.tfvars` or upgrading the CLI.

1.  **Update**:
    ```bash
    apim update
    ```
    *This runs `terraform apply` to converge any configuration drift.*

### 3. Import Existing (Adoption)
Adopt an existing Apigee Organization into Terraform state management.

1.  **Import**:
    Provide the Project ID and the template that matches the existing configuration.
    ```bash
    apim import my-existing-project-id us-central1
    ```
    *This generates `terraform.tfvars`, bootstraps identity, and imports the Organization resource.*

2.  **Align**:
    Run update to import remaining resources and align configuration.
    ```bash
    apim update
    ```

### 4. Verify & Test
Run automated integration tests to ensure your proxies are accessible.
```bash
apim apis test --proxy-name weather-api --bundle ./apiproxies/weather-api
```

---

## Configuration Reference (`terraform.tfvars`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `gcp_project_id` | **Required.** Target GCP Project ID. | N/A |
| `apigee_billing_type` | Billing level (EVALUATION/PAYG). | `EVALUATION` |
| `control_plane_location` | Control plane jurisdiction (e.g., `"ca"`). | `""` (Global) |
| `state_suffix` | Optional suffix to isolate multiple deployments in one project. | `null` |

---

## Common Issues

### "Billing type EVALUATION is not allowed"
**Cause**: You requested Data Residency (`control_plane_location="ca"`) but the project is in a legacy Evaluation state.
**Fix**: Link a valid billing account or move to a fresh Google Cloud Project.

### "Error 403: USER_PROJECT_DENIED" (during init/bootstrap)
**Cause**: Terraform is trying to enable APIs on a fresh project, but your ADC credentials are trying to bill that disabled project for the API call itself.
**Fix**: Set a "healthy" quota project (like your `ai-gateway` or sandbox) to absorb the API enablement costs:
```bash
gcloud auth application-default set-quota-project <healthy-project-id>
```


---

## See Also
- [CONTRIBUTING.md](CONTRIBUTING.md) for engineering practices, design principles, and the **"No Ad-hoc gcloud"** rule.