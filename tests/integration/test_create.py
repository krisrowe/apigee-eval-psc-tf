import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_create_existing_org_negative(existing_org_project_id, tmp_path):
    """
    Negative Scenario: Try to Create an Org where one already exists.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        template = {
            "billing_type": "EVALUATION",
            "drz": False,
            "runtime_location": "us-central1",
            "analytics_region": "us-central1"
        }
        Path("t.json").write_text(json.dumps(template))
        
        result = runner.invoke(cli, ["create", existing_org_project_id, "t.json"])
        
        assert result.exit_code != 0
        # Terraform Error for existing resource usually looks like:
        # "Error: google_apigee_organization.org: ... already exists"
        # We check for both parts to be specific.
        assert "google_apigee_organization" in result.output
        assert "already exists" in result.output

def test_create_no_org_positive(no_org_project_id, tmp_path):
    """
    Positive Scenario: Create a fresh Apigee Org.
    """
    pytest.skip("Skipping long-running create test by default to save time/cost. Run manually if needed.")
    
    # runner = CliRunner()
    # with runner.isolated_filesystem(temp_dir=tmp_path):
    #     template = { ... }
    #     ... invoke create ...
    #     assert result.exit_code == 0 
