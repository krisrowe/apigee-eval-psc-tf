# Apigee Terraform Provisioning

This repository provides a production-grade Terraform framework for deploying Apigee X/Hybrid on Google Cloud. It focuses on **State Convergence** rather than simple scripts, ensuring your infrastructure always matches your intent.

## Installation

```bash
make install
```
This installs the `apim` CLI tool to your system path.

---

## Quick Start

### 🟢 Scenario 1: New Project (Greenfield)
You have a fresh GCP project and want to deploy Apigee.

1.  **Configure Project:** Create a `terraform.tfvars` file in your working directory.
    ```hcl
    gcp_project_id = "my-project-id"
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
    *   **Phase 0:** Bootstraps Identity (Service Account, IAM).
    *   **Phase 1:** Creates Network, Apigee Organization, Instance, and Environments.

### 🟡 Scenario 2: Existing Project (Adoption)
You have an existing Apigee installation and want to manage it with this tool.

1.  **Hydrate State:** Run `import` to discover and adopt existing resources.
    ```bash
    apim import my-project-id
    ```
    *   *Note:* This command automatically generates `terraform.tfvars` if missing.

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
| `--auto-approve` | Skip interactive plan confirmation (useful for CI/CD). |
| `--skip-apigee` | **Network-Only Mode.** Provisions IAM and Networking (VPC, PSC) but skips Apigee Organization creation. Useful for staged rollouts or testing network paths. |
| `--bootstrap-only` | **Identity-Only Mode.** Runs Phase 0 (Service Account & IAM) and exits. Does not touch infrastructure. |

### `apim import [PROJECT_ID]`
Discovers existing Google Cloud resources and imports them into the local Terraform state.

| Flag | Description |
|---|---|
| `--force` | Overwrites local `terraform.tfvars` if it already exists. |

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

**Key Fields:**
*   `drz`: Must be `true`.
*   `analytics_region`: Must be omitted.
*   `control_plane_location`: Where the management plane lives (e.g., `ca`, `eu`).
*   `consumer_data_region`: Where the data lives (must match runtime location usually).

---

## Scenario Matrix & Test Coverage

| ID | CMD | TPL | LOCAL | CLOUD | Expected Outcome | Type | Method | P/F | Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- | :---: | :--- |
| **1** | 🚀 | ✅ | ⭕ | ⭕ | "Convergence Complete" | 🔵 | `test_apply_with_template_no_state_empty_cloud_mocked_org` | ✅ | 🆗 Sufficient |
| **2** | 🚀 | ✅ | ⭕ | 🟡 | "Convergence Complete" | 🔵 | `test_apply_with_template_no_state_empty_cloud_bootstrap_only` | ✅ | 🆗 Sufficient |
| **3** | 🚀 | ✅ | ⭕ | 🟡 | Error: 409 (Collision) | 🔵 | `test_apply_with_template_no_state_partial_cloud_mock_collision` | ✅ | 🆗 Verified |
| **4** | 🚀 | ✅ | ⭕ | 🟢 | Error: 409 (Collision) | - | *Covered by Scenario 3 Logic* | - | 🆗 Verified |
| **5** | 🚀 | ⛔ | ⭕ | 🟡 | Error: 409 (Collision) | - | *Covered by Scenario 3 Logic* | - | 🆗 Verified |
| **6** | 🚀 | ⛔ | ⭕ | 🟢 | Error: 409 (Collision) | - | *Covered by Scenario 3 Logic* | - | 🆗 Verified |
| **7** | 🚀 | ⛔ | 🟢 | 🟢 | Terraform Plan (Drift) | - | *Core Terraform Behavior (Drift)* | - | 🆗 Handled |
| **8** | 🚀 | ⛔ | 🟢 | 🟢 | Error: prevent_destroy | 🧪 | `test_apply_template_mismatch_existing_state_full_cloud` | ✅ | 🆗 Safe Block |
| **9** | 🚀 | ❌ | ⭕ | ⭕ | Error: "For new projects..." | 🧪 | `test_apply_no_template_no_state_empty_cloud_fails` | ✅ | 🆗 Sufficient |
| **10**| 🚀 | ❌ | ⭕ | 🟢 | Error: "For existing... import" | 🧪 | *Covered by Scenario 9 Logic* | ✅ | 🆗 Sufficient |
| **11**| 🚀 | ❌ | 🟢 | ⭕ | Terraform Plan (Recreate) | - | *Core Terraform Behavior (Refresh)* | - | 🆗 Handled |
| **12**| 🚀 | ❌ | 🟢 | 🟢 | "Convergence Complete" | 🟢 | `test_deny_deletes_enforcement` | ✅ | 🆗 Verified |
| **13**| 🔍 | ❌ | ⭕ | ⭕ | Error: "Not found in cloud" | 🧪 | `test_import_no_state_partial_cloud_resilient` | ✅ | 🆗 Verified |
| **14**| 🔍 | ❌ | ⭕ | 🟢 | "State Hydrated Successful" | 🧪 | `test_import_no_state_existing_cloud_success` | ✅ | ⚠️ Needs Integ |
| **15**| 🔍 | ❌ | 🟢 | 🟢 | "State Hydrated Successful" | - | *Idempotency Check* | - | 🆗 Handled |

### Legend

**Inputs/State:**
- **CMD**: 🚀 `apply` | 🔍 `import`
- **TPL**: ✅ `compatible/match` | ⛔ `mismatch/conflict` | ❌ `not provided`
- **LOCAL/CLOUD**: ⭕ `empty` | 🟢 `full/org` | 🟡 `partial/shared`

**Test Status:**
- 🟢 **Full Integration**: End-to-end against real GCP infrastructure.
- 🔵 **Partial Integration**: Real bootstrap (Phase 0) + Mocked Org (Phase 1).
- 🧪 **Unit Test**: Python logic verification w/ full mocking.
- 🆗 **Sufficient**: Core logic verified. | ⚠️ **Insufficient**: Manual verification required.

### Test Coverage Notes
*   **Core Terraform Behavior:** Scenarios relying on standard Terraform mechanics (e.g., `refresh` detecting missing resources, `plan` detecting immutable conflicts) are handled by the engine. The CLI's role is ensuring correct variable injection.
*   **Safe Destruction Block:** Immutable fields (Region, Billing) are protected by `prevent_destroy = true` in the Terraform source. Mismatching templates will trigger a Plan Error rather than an accidental deletion.
*   **Collision Handling:** The CLI strictly separates Creation (`apply`) and Adoption (`import`). If `apply` encounters an existing resource without local state, it will fail with a Terraform 409 error. The user must run `import` to resolve this.

---

## Configuration

**Strict Policy:** `terraform.tfvars` must contain **ONLY** `gcp_project_id`. All other settings are managed via Templates or State Extraction.

```hcl
gcp_project_id = "my-project-id"
```

---

## See Also
- [CONTRIBUTING.md](CONTRIBUTING.md) for design principles and the **"No Ad-hoc gcloud"** rule.
