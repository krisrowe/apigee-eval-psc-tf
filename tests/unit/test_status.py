import pytest
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_status_project_not_found(tmp_path):
    """'apim status' should error if no project ID is found in CWD."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["status"])
        assert result.exit_code != 0
        assert "No project ID found" in result.output

def test_status_success(cloud_provider, tmp_path):
    """'apim status' should display information from the state via provider."""
    project_id = "test-project"
    
    # Setup Mock State
    cloud_provider.orgs[project_id] = {
        "billing_type": "PAYG",
        "subscription_type": "PAID",
        "api_consumer_data_location": "northamerica-northeast1"
    }
    cloud_provider.instances[project_id] = [{"name": "inst-1", "location": "northamerica-northeast1"}]
    cloud_provider.environments[project_id] = ["dev"]

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create config
        Path("terraform.tfvars").write_text(f'gcp_project_id = "{project_id}"\n')
        
        # We need to simulate the state file existence for the provider to work
        # The provider looks for root / project_id / "tf" / "1-main" / "terraform.tfstate"
        import os
        from scripts.cli.paths import get_state_path
        state_file = get_state_path(project_id)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text('{"resources": []}') # Dummy state, mock provider will handle data

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        
        # Strip ANSI codes
        import re
        clean_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result.output)
        
        assert f"ENVIRONMENT STATUS: {project_id}" in clean_output
        assert "Billing:               PAYG" in clean_output
        assert "DRZ:                   Yes" in clean_output
        assert "Control Plane:         ca" in clean_output
        assert "✓ Environments: dev" in clean_output