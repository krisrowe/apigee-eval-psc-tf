import json
import pytest
import subprocess
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from scripts.cli.paths import get_state_path

def test_import_existing_org_positive(existing_org_project_id, tmp_path):
    """
    Positive Scenario: Import an existing Apigee Org.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["import", existing_org_project_id])
        assert result.exit_code == 0
        assert "State Hydrated Successful" in result.output

@pytest.mark.integration
def test_import_with_project_id_no_state_partial_cloud_discovery(ephemeral_project, tmp_path):
    """
    Scenario: Discovery of existing infrastructure.
    1. Pre-seed a VPC Network via gcloud.
    2. Run `apim import`.
    3. Validate that the Network is adopted into the local tfstate file.
    """
    # 1. Pre-Seed Network
    subprocess.run([
        "gcloud", "compute", "networks", "create", "apigee-network",
        "--project", ephemeral_project,
        "--subnet-mode", "auto",
        "--quiet"
    ], check=True)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 2. Run Import
        result = runner.invoke(cli, ["import", ephemeral_project])
        assert result.exit_code == 0
        assert "Imported google_compute_network.apigee_network" in result.output

        # 3. Validate State File content directly
        # We use the centralized path logic to find the file the CLI just created
        state_path = get_state_path(ephemeral_project, phase="1-main")
        assert state_path.exists()
        
        with open(state_path, "r") as f:
            state = json.load(f)
            
        resources = [r["type"] for r in state.get("resources", [])]
        assert "google_compute_network" in resources

def test_import_no_org_negative(no_org_project_id, tmp_path):
    """
    Negative Scenario: Try to Import an Org that doesn't exist.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["import", no_org_project_id])
        # Should succeed with warnings about missing Org
        assert result.exit_code == 0
        assert "Warning: Apigee Organization was not found" in result.output