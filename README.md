# Apigee Terraform Provisioning

This repository provides a production-grade Terraform framework for deploying Apigee X/Hybrid on Google Cloud. It focuses on **State Convergence** rather than simple scripts, ensuring your infrastructure always matches your intent.

## Installation

```bash
make install

# See available commands and options
apim
```

---

## Prerequisites & Setup

Before using `apim`, ensure you have a Google Cloud Project with billing enabled.

1.  **Authenticate:**
    ```bash
    # Authenticates the gcloud CLI (used by the apim wrapper for API checks)
    gcloud auth login

    # Authenticates Terraform (the underlying engine)
    gcloud auth application-default login
    ```
    *Requirement:* You currently need **Organization Admin** or **Billing Admin** privileges to create new projects and link billing.

2.  **Create a Project (Optional):**
    ```bash
    export PROJECT_ID="my-new-apigee-project"
    gcloud projects create $PROJECT_ID
    ```

3.  **Link Billing:**
    Find your Billing Account ID:
    ```bash
    gcloud billing accounts list
    ```
    Link it to your project:
    ```bash
    export BILLING_ID="012345-6789AB-CDEF01"
    gcloud billing projects link $PROJECT_ID --billing-account $BILLING_ID
    ```

---

## Quick Start

### 🟢 Scenario 1: New Project (Greenfield)
You have a fresh GCP project and want to deploy Apigee.

1.  **Configure Project:**
    Initialize the local directory:
    ```bash
    apim project set my-project-id
    ```

2.  **Define Template:** Create a `template.json` to define your desired Apigee state.
    ```json
    {
      "billing_type": "PAYG",
      "runtime_location": "us-central1",
      "analytics_region": "us-central1"
    }
    ```

3.  **Initialize:** Run `apply` with your template.
    ```bash
    apim apply template.json
    ```

### 🟡 Scenario 2: Existing Project (Adoption)
You have an existing Apigee installation and want to manage it with this tool.

1.  **Hydrate State:**
    Run `import` to discover existing resources:
    ```bash
    apim import my-project-id
    ```
    *   *Note:* Use `--control-plane=ca` (or eu, au) for regional Data Residency projects.

2.  **Converge:** Run `apply` (no template) to align configuration with reality.
    ```bash
    apim apply
    ```

---

## CLI Reference

### `apim apply [TEMPLATE]`
Provisions or updates infrastructure. If a template is provided, it enforces that state. If not, it extracts configuration from the existing state.

| Flag | Description |
|---|---|
| `--interactive` | Prompt for approval before applying changes. Default is **False** (Auto-approve). |
| `--skip-apigee` | **Network-Only Mode.** Provisions IAM and Networking (VPC, PSC) but skips Apigee Organization creation (45m). |
| `--bootstrap-only` | **Identity-Only Mode.** Runs Phase 0 (Service Account & IAM) and exits. |

### `apim import [PROJECT_ID]`
Discovers existing Google Cloud resources and imports them into the local Terraform state.

| Flag | Description |
|---|---|
| `--control-plane` | Specify the regional control plane (e.g., `ca`, `eu`). Required for finding DRZ Orgs. |
| `--force` | Overwrites local `terraform.tfvars` if it already exists. |

### `apim project set [PROJECT_ID]`
Updates the local `terraform.tfvars` with a new Project ID and checks for existing state. Use `--force` to overwrite.

---

## Advanced Configuration

### Data Residency (DRZ) Template
For regions requiring Data Residency (e.g. Canada, Europe), use a specific template structure.

**`drz-template.json`:**
```json
{
  "billing_type": "PAYG",
  "drz": true,
  "runtime_location": "northamerica-northeast1",
  "control_plane_location": "ca",
  "consumer_data_region": "northamerica-northeast1"
}
```

---

## Scenario Matrix & Test Coverage

| ID | CMD | TPL | LOCAL | CLOUD | Expected Outcome | Type | Method | P/F | Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- | :---: | :--- |
| **1** | 🚀 | ✅ | ⭕ | ⭕ | "System Converged" | 🔵 | `test_apply_..._mocked_org` | ✅ | 🆗 Sufficient |
| **1b**| 🚀 | ✅ | ⭕ | ⭕ | "System Converged" | 🟢 | `test_apply_..._skip_apigee` | ✅ | 🆗 Verified |
| **2** | 🚀 | ✅ | ⭕ | 🟡 | "System Converged" | 🟢 | `test_apply_..._bootstrap_only` | ✅ | 🆗 Verified |
| **3** | 🚀 | ✅ | ⭕ | 🟡 | Error: 409 (Collision) | 🔵 | `test_apply_..._mock_collision` | ✅ | 🆗 Verified |
| **4** | 🚀 | ✅ | ⭕ | 🟢 | Error: 409 (Collision) | 🟢 | `test_apply_..._existing_cloud_org` | ✅ | 🆗 Verified |
| **12**| 🚀 | ❌ | 🟢 | 🟢 | "System Converged" | 🟢 | `test_deny_deletes_enforcement` | ✅ | 🆗 Verified |
| **13**| 🔍 | ❌ | ⭕ | ⭕ | Error: "Not found" | 🟢 | `test_import_no_org_negative` | ✅ | 🆗 Verified |
| **14**| 🔍 | ❌ | ⭕ | 🟢 | "State Hydrated Successful" | 🟢 | `test_import_..._discovery` | ✅ | 🆗 Verified |
| **15**| 🔍🚀| ✅ | ⭕ | 🟡 | "System Converged" | 🟢 | `test_import_apply_..._fill_blanks` | ✅ | 🆗 Verified |

### Legend
- 🚀 `apply` | 🔍 `import`
- 🟢 **Full Integration**: End-to-end against real GCP.
- 🔵 **Partial Integration**: Real bootstrap + Mocked Main.
- 🧪 **Unit Test**: Python logic verification.

---

## See Also
- [CONTRIBUTING.md](CONTRIBUTING.md) for design principles and the **"No Ad-hoc gcloud"** rule.