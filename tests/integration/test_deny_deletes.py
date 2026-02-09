import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path

@pytest.mark.integration
def test_deny_deletes_enforcement(existing_org_project_id, tmp_path):
    """
    Integration Test: Verify IAM Deny Policy enforcement.
    Invokes the CLI command 'apim tests run deny-deletes' to ensure the user-facing command works.
    """
    
    # Setup Config in tmp_path (FLAT structure)
    tfvars_content = f"""
gcp_project_id          = "{existing_org_project_id}"
apigee_runtime_location = "us-central1"
apigee_analytics_region = "us-central1"
apigee_billing_type     = "PAYG"
control_plane_location  = "us"
project_nickname        = "integration-test"
"""
    (tmp_path / "terraform.tfvars").write_text(tfvars_content)
    
    # Run the CLI command
    runner = CliRunner()
    
    # We must run it inside the tmp_path so it finds the config
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["tests", "run", "deny-deletes"])
        
        # Output debug info on failure
        if result.exit_code != 0:
            print(result.output)
            
        assert result.exit_code == 0
        assert "ALL TESTS PASSED" in result.output