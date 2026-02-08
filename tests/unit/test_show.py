import os
import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path

def test_show_displays_cloud_status(cloud_provider, tmp_path):
    """
    'apim show' should display organization status when found.
    """
    # 1. Setup Mock Cloud State
    project_id = "test-project"
    cloud_provider.orgs[project_id] = {"name": project_id}
    cloud_provider.environments[project_id] = ["dev", "prod"]
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create dummy config
        Path("apigee.tfvars").write_text(f'gcp_project_id = "{project_id}"\n')
        
        result = runner.invoke(cli, ["show"])
        
        assert result.exit_code == 0
        assert "CLOUD STATUS (Live API):" in result.output
        assert "✓ Apigee Organization found." in result.output
        assert "Environments: dev, prod" in result.output
