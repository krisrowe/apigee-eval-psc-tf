# Apigee Terraform Provisioning

This repository provides a specialized Terraform framework for deploying **Apigee X** on Google Cloud. It focuses on **State Convergence** rather than simple scripts, ensuring your infrastructure always matches your intent.

### The Apigee Deployment Workspace (ADW)
The core unit of management in this framework is the **Apigee Deployment Workspace (ADW)**. An ADW is a local directory containing a `terraform.tfvars` configuration and any associated deployment assets (like API Proxy bundles). Each ADW maps 1:1 to a specific Apigee Organization and GCP Project, providing a strict isolation boundary that prevents configuration bleed and state collisions across your Apigee fleet.

It is designed as a **Rapid Starter** for managing quick installations and repairing reference implementations. It captures the idiosyncrasies of managing Apigee with Terraform, navigating complex patterns such as:
*   **Data Residency (DRZ):** Handling regional control planes and consumer data location.
*   **Networking:** Configuring Northbound (Ingress/PSC) and Southbound (VPC Peering/PSA) connectivity.
*   **Custom Domains:** Aligning public ingress with Apigee Environment Groups.
*   **Safety:** Preventing accidental deletion of immutable "pet" infrastructure (Organization, Instance) via state protection.

One beauty of this framework is that, unlike raw Terraform, it allows you to **recover and manage an existing installation** through custom `tf import` logic. This makes local state files "less precious" and casual environment management significantly less complex and demanding.

Furthermore, the architecture allows for **seamless extension via additional .tf modules** for specific scenarios (e.g., AI Gateway). This enables configuring the various GCP resources that Apigee integrates with for those use cases without having to duplicate the core Apigee configuration itself.

This framework serves as a solid foundation for broader, enterprise-grade implementations that can be extended to multiple regions and complex topologies.

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

The `apim` CLI is designed to manage the full lifecycle of an Apigee deployment using a local **Apigee Deployment Workspace (ADW)** for each Apigee Organization or GCP Project—from infrastructure provisioning to API delivery and fleet-wide visibility.

### Fleet Visibility & Context Management

#### `apim list`
Displays a fleet-wide overview of all ADWs known to your local machine. This provides a quick, tabular dashboard of billing types, control planes, and runtime regions across multiple GCP projects without needing to navigate the Google Cloud Console.

#### `apim show` & `apim status`
Orient yourself before making changes. 
*   `apim show` details the configuration of your current active directory and lists all infrastructure resources currently tracked by the tool.
*   `apim status` queries the live Apigee Management API to confirm operational health, reporting on instance readiness, environment attachments, and SSL provisioning.

#### `apim project set [PROJECT_ID]`
Updates the local `terraform.tfvars` with a new Project ID. This locks your current directory to a specific cloud deployment, creating an isolated ADW.

---

### Infrastructure Provisioning

#### `apim apply [TEMPLATE]`
Provisions or updates infrastructure. If a template is provided, it enforces that state. If not, it extracts configuration from the existing state.

| Flag | Description |
|---|---|
| `--interactive` | Prompt for approval before applying changes. Default is **False** (Auto-approve). |
| `--skip-apigee` | **Network-Only Mode.** Provisions IAM and Networking (VPC, PSC) but skips Apigee Organization creation (45m). |
| `--bootstrap-only` | **Identity-Only Mode.** Runs Phase 0 (Service Account & IAM) and exits. |
| `--skip-impersonation` | Uses your Application Default Credentials (ADC) directly instead of impersonating the deployment service account. |

#### `apim import [PROJECT_ID]`
Discovers existing Google Cloud resources and securely adopts them into the local state, allowing you to manage brownfield environments.

| Flag | Description |
|---|---|
| `--control-plane` | Specify the regional control plane (e.g., `ca`, `eu`). Required for finding Data Residency organizations. |

---

### API Lifecycle

#### `apim apis deploy [PROXY_NAME]` & `apim apis test [PROXY_NAME]`
Bridges the gap between infrastructure and delivery. Deploy proxy bundles directly from your ADW to your provisioned environments and execute automated integration tests to verify southbound connectivity and policy execution.

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

## Known Issues
*   **Concurrency:** The CLI disables Terraform state locking (`-lock=false`) to ensure a smooth local experience. Avoid running multiple convergence operations against the same project simultaneously.
*   **Standard Naming:** Adoption discovery (`apim import`) assumes standard environment (`dev`) and group (`eval-group`) names. Projects with custom naming may require manual `terraform import` for some resources.

---

## Developing API Proxies

When developing and testing API Proxies or Shared Flows, we recommend organizing your project assets within an **Apigee Deployment Workspace (ADW)**—the local directory containing your `terraform.tfvars` configuration. We rely on static analysis tools to ensure bundle integrity before deployment. 

For documentation on how to structure your ADW and how to use tools like `apigeelint` for validation, see the **[API Proxy Development Guide](docs/API-PROXIES.md)**.

---

## See Also
- [CONTRIBUTING.md](CONTRIBUTING.md) for design principles and the **"No Ad-hoc gcloud"** rule.