# Contributing to apigee-tf

This document outlines the engineering practices, design principles, and contributor guidelines for the `apigee-tf` repository.

## Engineering Principles

### 1. Repeatable Infrastructure (No Ad-hoc Reconfigurations)
> [!IMPORTANT]
> **Do not ever run `gcloud services enable` or manually grant IAM permissions via the console/CLI for the purpose of "fixing" an environment managed by this repo.**

All infrastructure requirements (service enablement, IAM roles, networking) MUST be defined in Terraform. This ensures:
- **Repeatability**: Anyone can provision a fresh environment from scratch.
- **Traceability**: Changes are captured in git history.
- **Consistency**: Environments (Dev/Test/Prod) don't drift.

### 2. Smart Defaulting
The CLI and Terraform modules follow the principle of **"Implicitly Correct Defaults"**:
- **Billing**: Defaults to `EVALUATION`.
- **Auto-Upgrade**: If Data Residency (DRZ) is requested (`control_plane_location` is set), the billing type is automatically upgraded to `PAYG` to satisfy GCP requirements with minimal user boilerplate.

### 3. State Management
This repository uses a **Project-ID Centric** state management model:
- State files are stored locally at `~/.local/share/apigee-tf/states/`.
- The primary filename is the `gcp_project_id`.
- **Isolating Segments**: If a single GCP project hosts multiple independent Apigee deployments (e.g., `sandbox` and `roles`), use the `state_suffix` variable to prevent state collisions.

## Configuration Guidelines

### Strict File Policy
To maintain consistency and avoid confusion with Terraform conventions:
*   **Allowed:** `terraform.tfvars`
*   **Forbidden:** `apigee.tfvars` (Support is removed)
*   **Content:** Keep configuration minimal. Rely on defaults in `variables.tf` or Template JSONs where possible.
    *   **Required:** `gcp_project_id`
    *   **Optional:** `apigee_runtime_location`, `apigee_billing_type`, etc.

### Config Loading Logic
The CLI `ConfigLoader` reads `terraform.tfvars`, validates the project ID, and passes it to the engine. The engine then synthesizes the full Terraform configuration (backend, providers, variables) in the staging directory.

## Development Workflow

### Testing (TDD)
- We follow Test-Driven Development. Create a test case in `tests/` that asserts the desired behavior before implementing the fix/feature.
- Run tests via `make test`.

### Security Checks
Before committing, ensure you run:
- `consult precommit`: Scans for sensitive identifiers and PII.
- `devws precommit`: Checks git history integrity.

## Identity & Bootstrap Model

This project follows a **Two-Phase Identity Handoff** model:

1.  **Phase 0 (Bootstrap):** Executes as the **User Identity** (via ADC). This phase is responsible for creating the Service Account (`terraform-deployer`) and granting it necessary IAM permissions (Project Owner).
2.  **Phase 1 (Main):** Executes as the **Service Account Identity** (via Impersonation). This phase provisions the Apigee infrastructure.

### Continuous Bootstrap
To ensure maximum reliability and "Self-Healing" access, the CLI executes **Phase 0 (Bootstrap) on every invocation** of `apply` or `import`.

**Rationale:**
- **Active Repair:** If the Service Account or its IAM bindings are accidentally deleted or modified in the cloud, the CLI automatically restores them during the next `apply` cycle.
- **Immediate Grant:** The bootstrap phase explicitly grants the current user the `roles/iam.serviceAccountTokenCreator` role on the new SA, ensuring that impersonation handoff works immediately even on fresh projects.
- **Idempotency:** Standard Terraform `apply` mechanics ensure this check is fast (5-10s) and non-destructive if no changes are required.

### Internal Testing Flags
The CLI includes hidden flags primarily used by the integration test suite to verify safety mechanisms.

| Flag | Purpose |
|---|---|
| `--fake-secret` | Creates a dummy Secret Manager resource. Used by `test_deny_deletes.py` to verify IAM policies block deletion. |
| `--deletes-allowed` | Temporarily disables the IAM Deny Policy. Used by tests to clean up resources after verifying the block. |
| `--skip-impersonation` | **Deprecated/Debug Only.** Forces the CLI to use ADC credentials for Phase 1 instead of the Service Account. Useful if IAM propagation is blocked in a specific environment. |

## Integration Testing

Integration tests run against **REAL** Google Cloud Platform projects. They are located in `tests/integration/` and are excluded from the default `make test` command (which runs unit tests only).

### Prerequisites

### Prerequisites

To run integration tests, you need target GCP projects. You can define these via **Environment Variables** (explicit) or **Labels** (auto-discovery).

#### Option A: Environment Variables (Recommended for CI)

| Variable | Description |
|---|---|
| `EXISTING_APIGEE_ORG_PROJECT_ID` | Project ID that **already has** a fully provisioned Apigee Organization. Used to test `import` and `update` idempotency. |
| `NO_APIGEE_ORG_PROJECT_ID` | Project ID that has **NO** Apigee Organization (but has Billing and APIs enabled). Used to test `create` (Note: `create` takes ~45m). |

#### Option B: Auto-Discovery via Labels (Recommended for Devs)

The test runner can automatically find projects if you label them using `gcloud`:

1. **Existing Org Project**:
   ```bash
   gcloud projects add-labels my-existing-proj --labels=apigee-tf=integration-test
   ```

2. **No Org Project** (Empty/Clean):
   ```bash
   gcloud projects add-labels my-missing-proj --labels=apigee-tf=missing
   ```

### Running Tests

Run integration tests explicitly using `pytest`:

```bash
# Run all integration tests (will skip if no projects found)
pytest tests/integration

# Run with output to see which projects are selected
pytest tests/integration -s
```

> [!WARNING]
> Integration tests invoke real Terraform commands (`apply`, `import`) which **will modify infrastructure** and **incur costs**. Ensure you are using non-production sandbox projects.

## Architecture & Performance Note

### Ephemeral Staging
As of the "Centralized Status & Coarse-Grained Provider" refactor:
*   **Staging:** `~/.cache/apigee-tf/` (Ephemeral - wiped on every run)
*   **State:** `~/.local/share/apigee-tf/states/` (Persistent)

**Trade-off:**
*   **Correctness (Gain):** Wiping the staging directory ensures no stale symlinks or artifacts (like `.terraform/`) corrupt the run. It guarantees that `apim plan` reflects exactly the current code/config.
*   **Performance (Loss):** `terraform init` re-downloads provider plugins on every execution (~15-30s overhead).

**Future Optimization:**
To restore performance without sacrificing correctness, we can implement a Global Plugin Cache by setting `TF_PLUGIN_CACHE_DIR` in the CLI engine. This is a known optimization path if build times become an issue.

## Future Enhancements
*   **Broadened Role Support:** Future versions aim to support standard **Project Owners** and consumer **@gmail.com** accounts, removing the strict requirement for Organization Admin privileges during the bootstrap phase.
*   **Import Block Generation:** Replace `terraform import` loops with declarative `import { ... }` blocks for more robust state adoption.
