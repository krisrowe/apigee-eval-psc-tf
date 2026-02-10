# Apigee Terraform Provisioning

This repository provides a production-grade Terraform framework for deploying Apigee X/Hybrid on Google Cloud. It focuses on **State Convergence** rather than simple scripts, ensuring your infrastructure always matches your intent.

## Quick Start

### 🟢 Scenario 1: New Project (Greenfield)
You have a fresh GCP project and want to deploy Apigee.

1.  **Initialize**: Run `apply` with your desired template.
    ```bash
    # Usage: apim apply [TEMPLATE]
    apim apply ca-drz
    ```

### 🟡 Scenario 2: Existing Project (Adoption)
You have an existing Apigee installation and want to manage it with this tool.

1.  **Hydrate State**: Run `import` to discover and adopt existing resources.
    ```bash
    apim import my-project-id
    ```
2.  **Converge**: Run `apply` (no template).
    ```bash
    apim apply
    ```

---

## Scenario Matrix & Test Coverage

| ID | CMD | TPL | LOCAL | CLOUD | Expected Outcome | Type | Method | P/F | Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- | :---: | :--- |
| **1** | 🚀 | ✅ | ⭕ | ⭕ | "Convergence Complete" | 🔵 | `test_apply_template_on_empty_project_full_flow` | ✅ | 🆗 Sufficient |
| **2** | 🚀 | ✅ | ⭕ | 🟡 | "Convergence Complete" | 🔵 | `test_apply_template_on_empty_project_bootstrap_only` | ✅ | 🆗 Sufficient |
| **3** | 🚀 | ✅ | ⭕ | 🟡 | "Convergence Complete" | 🧪 | `test_apply_with_template_no_state_partial_cloud_adopts_network` | ✅ | 🆗 Sufficient |
| **4** | 🚀 | ✅ | ⭕ | 🟢 | "Convergence Complete" | 🟢 | `test_apply_with_template_no_state_existing_cloud_org` | ✅ | 🆗 Sufficient |
| **5** | 🚀 | ⛔ | ⭕ | 🟡 | Error: prevent_destroy | 🔵 | `test_apply_template_mismatch_no_state_existing_cloud` | ✅ | 🆗 Safe Block |
| **6** | 🚀 | ⛔ | ⭕ | 🟢 | Error: prevent_destroy | 🔵 | `test_apply_template_mismatch_no_state_existing_cloud` | ✅ | 🆗 Safe Block |
| **7** | 🚀 | ⛔ | 🟢 | 🟢 | Terraform Plan (Drift) | - | *Core Terraform Behavior (Drift)* | - | 🆗 Handled |
| **8** | 🚀 | ⛔ | 🟢 | 🟢 | Error: prevent_destroy | 🧪 | `test_apply_template_mismatch_existing_state_full_cloud` | ✅ | 🆗 Safe Block |
| **9** | 🚀 | ❌ | ⭕ | ⭕ | Error: "For new projects..." | 🧪 | `test_apply_no_template_no_state_empty_cloud_fails` | ✅ | 🆗 Sufficient |
| **10**| 🚀 | ❌ | ⭕ | 🟢 | Error: "For existing... import" | 🧪 | *Covered by Scenario 9 Logic* | ✅ | 🆗 Sufficient |
| **11**| 🚀 | ❌ | 🟢 | ⭕ | Terraform Plan (Recreate) | - | *Core Terraform Behavior (Refresh)* | - | 🆗 Handled |
| **12**| 🚀 | ❌ | 🟢 | 🟢 | "Convergence Complete" | 🟢 | `test_deny_deletes_enforcement` | ✅ | 🆗 Sufficient |
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
*   **State Drift:** Cases where **LOCAL** state mismatches **CLOUD** state (but TPL matches Cloud) are not listed separately because Terraform `refresh` automatically harmonizes the State with the Cloud before planning.
*   **Safety Errors:** Scenario 10 occurs when a user tries to converge on an existing project without first running `import` or providing a template. The CLI is designed to block this and advise hydration.

---

## Installation

```bash
make install
```

## Configuration

**Strict Policy:** `terraform.tfvars` must contain **ONLY** `gcp_project_id`. All other settings are managed via Templates or State Extraction.

```hcl
gcp_project_id = "my-project-id"
```

---

## See Also
- [CONTRIBUTING.md](CONTRIBUTING.md) for design principles and the **"No Ad-hoc gcloud"** rule.