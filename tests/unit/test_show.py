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

import re

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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
        clean_output = strip_ansi(result.output)
        assert "CLOUD STATUS (via Terraform State):" in clean_output
        assert "Billing:         EVALUATION" in clean_output
        assert "DRZ:             No" in clean_output
        assert "✓ Environments: dev, prod" in clean_output