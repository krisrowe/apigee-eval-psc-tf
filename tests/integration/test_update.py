import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_update_existing_org(existing_org_project_id, tmp_path):
    """
    Validation of 'apim update' behavior with various config inputs.
    Pre-requisite: Project must ALREADY have an Apigee Org.
    """
    runner = CliRunner()
    
    # --- Setup: We need to 'import' first to populate local state ---
    # We use a matching template so import succeeds and gives us a baseline `terraform.tfstate`.
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import_template = {
             "billing_type": "EVALUATION", 
             "drz": False,
             "runtime_location": "us-central1",
             "analytics_region": "us-central1"
        }
        Path("import.json").write_text(json.dumps(import_template))
        
        # 0. Initial Import (To get State)
        res = runner.invoke(cli, ["import", existing_org_project_id, "import.json"])
        if res.exit_code != 0:
             pytest.fail(f"Setup Failed: Import failed. {res.output}")

        # --- Scenario 1: Minimal Config (Project ID only) ---
        # No template fields. Should succeed (No-Op or Idempotent).
        Path("terraform.tfvars").write_text(f'gcp_project_id="{existing_org_project_id}"\n')
        
        print("\n[Test] Scenario 1: Update with Project ID only...")
        res = runner.invoke(cli, ["update", "--auto-approve"])
        assert res.exit_code == 0
        assert "Update Complete" in res.output

        # --- Scenario 2: Matching Config ---
        # Config matches the existing state (us-central1). Should succeed.
        Path("terraform.tfvars").write_text(
            f'gcp_project_id="{existing_org_project_id}"\n'
            f'apigee_analytics_region="us-central1"\n'
        )
        print("\n[Test] Scenario 2: Update with Matching Config...")
        res = runner.invoke(cli, ["update", "--auto-approve"])
        assert res.exit_code == 0
        assert "Update Complete" in res.output

        # --- Scenario 3: Conflicting Config (Immutable Field) ---
        # Config conflicts with existing state (us-east1 vs us-central1).
        # Should FAIL due to Terraform Precondition in main.tf.
        Path("terraform.tfvars").write_text(
            f'gcp_project_id="{existing_org_project_id}"\n'
            f'apigee_analytics_region="us-east1"\n'
        )
        print("\n[Test] Scenario 3: Update with Conflicting Config...")
        res = runner.invoke(cli, ["update", "--auto-approve"])
        
        assert res.exit_code != 0
        # Expecting the custom error message from main.tf precondition
        assert "Conflict!" in res.output or "precondition_failed" in res.output

def test_update_no_org_negative(no_org_project_id, tmp_path):
    """
    Negative Scenario: Try to Update an Org that doesn't exist.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text(f'gcp_project_id="{no_org_project_id}"\n')
        
        # No local state exists in this fresh temp dir.
        result = runner.invoke(cli, ["update"])
        
        assert result.exit_code != 0
        assert "No Apigee Organization found in local state" in result.output
