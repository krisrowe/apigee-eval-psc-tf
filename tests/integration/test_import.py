import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_import_existing_org_positive(existing_org_project_id, tmp_path):
    """
    Positive Scenario: Import an existing Apigee Org.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create a minimal template locally to satisfy import requirement
        template = {
            "billing_type": "EVALUATION", # Usually valid default for import checking
            "drz": False,
            "runtime_location": "us-central1", # Assumption, might need flexibility
            "analytics_region": "us-central1"
        }
        Path("t.json").write_text(json.dumps(template))
        
        # Run import
        # Note: This runs real terraform import. It might fail if credentials aren't set up 
        # or if the user doesn't have permission. Assuming testing env has adc.
        result = runner.invoke(cli, ["import", existing_org_project_id, "t.json"])
        
        if result.exit_code != 0:
            # If it fails, print output for debugging
            print(f"Import Failed: {result.output}")
            
        assert result.exit_code == 0
        assert "Import Successful" in result.output
        assert Path("terraform.tfvars").exists()

def test_import_no_org_negative(no_org_project_id, tmp_path):
    """
    Negative Scenario: Try to Import an Org that doesn't exist.
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
        
        result = runner.invoke(cli, ["import", no_org_project_id, "t.json"])
        
        assert result.exit_code != 0
        assert "Apigee Organization not found" in result.output # We rely on our pre-check here
