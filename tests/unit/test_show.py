import pytest
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_show_displays_local_paths(tmp_path):
    """
    'apim show' should display local project configuration and state paths.
    """
    project_id = "test-project"
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text(f'gcp_project_id = "{project_id}"\n')
        
        result = runner.invoke(cli, ["show"])
        
        assert result.exit_code == 0
        assert "LOCAL PROJECT STATUS" in result.output
        assert "Config:" in result.output
        assert "terraform.tfvars" in result.output
        assert "State:" in result.output

def test_show_displays_cloud_status(cloud_provider, tmp_path):
    """
    'apim show' should display cloud status via provider when project is attached.
    """
    project_id = "test-project"
    
    # Setup Mock State for provider
    cloud_provider.orgs[project_id] = {
        "billing_type": "EVALUATION",
        "subscription_type": "TRIAL"
    }
    cloud_provider.instances[project_id] = [{"name": "eval-inst", "location": "us-central1"}]
    cloud_provider.environments[project_id] = ["dev", "prod"]

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text(f'gcp_project_id = "{project_id}"\n')
        
        # Simulate state file existence
        from scripts.cli.paths import get_state_path
        state_file = get_state_path(project_id)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text('{"resources": []}')

        result = runner.invoke(cli, ["show"])

        assert result.exit_code == 0
        assert "CLOUD STATUS (via Terraform State):" in result.output
        assert "Billing:         EVALUATION" in result.output
        assert "DRZ:             No" in result.output
        assert "✓ Environments: dev, prod" in result.output