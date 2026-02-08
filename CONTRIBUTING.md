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

## Development Workflow

### Testing (TDD)
- We follow Test-Driven Development. Create a test case in `tests/` that asserts the desired behavior before implementing the fix/feature.
- Run tests via `make test`.

### Security Checks
Before committing, ensure you run:
- `consult precommit`: Scans for sensitive identifiers and PII.
- `devws precommit`: Checks git history integrity.
