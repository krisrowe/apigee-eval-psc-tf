import json
import pytest
import subprocess
import time
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from unittest.mock import patch, MagicMock

# Helper to provide a conditional subprocess mock that allows Phase 0 but mocks heavy Phase 1
@pytest.fixture
def conditional_tf_mock():
    real_subprocess_run = subprocess.run

    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        cmd_str = " ".join(cmd)
        
        # If running in 1-main (Phase 1) AND NOT targeting the network, MOCK IT.
        # This allows us to test network collisions for real without creating the Org.
        if "1-main" in cwd:
            if "google_compute_network" not in cmd_str and "google_apigee_organization" in cmd_str:
                mock_res = MagicMock()
                mock_res.returncode = 0
                mock_res.stdout = "Mocked Phase 1 (Org) Success"
                return mock_res
                
        # Otherwise (Phase 0, Network creation, gcloud, etc.), Run for Real.
        return real_subprocess_run(cmd, **kwargs)
    
    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect) as mock:
        yield mock

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_bootstrap_only(ephemeral_project, tmp_path, conditional_tf_mock):
    """
    Scenario 2: apply [TPL] + No State + Empty Cloud.
    Verify Phase 0 handles shared identity logic.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        result = runner.invoke(cli, ["apply", "us-central1", "--bootstrap-only"])
        assert result.exit_code == 0
        assert "✓ Bootstrap complete" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_mocked_org(ephemeral_project, tmp_path, conditional_tf_mock):
    """
    Scenario 1: apply [TPL] + No State + Empty Cloud.
    Full flow verification with mocked Org.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
        assert result.exit_code == 0
        assert "✓ Bootstrap complete" in result.output
        assert "Convergence Complete" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_partial_cloud_mock_collision(ephemeral_project, tmp_path):
    """
    Scenario 3/9: apply [TPL] + No State + Existing Network.
    Expectation: FAILURE (409 Already Exists).
    We mock the collision response for speed and safety.
    """
    runner = CliRunner()
    
    # Capture real subprocess to allow Phase 0
    real_subprocess_run = subprocess.run

    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        
        # Phase 1: Simulate Collision
        if "1-main" in cwd:
            msg = "Error: google_compute_network.apigee_network already exists"
            print(msg) # Print so CliRunner captures it
            
            mock_res = MagicMock()
            mock_res.returncode = 1 # Error
            mock_res.stdout = msg
            return mock_res
            
        return real_subprocess_run(cmd, **kwargs)

    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
            
            result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
            
            assert result.exit_code != 0
            assert "already exists" in result.output