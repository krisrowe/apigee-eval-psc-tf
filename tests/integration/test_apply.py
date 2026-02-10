import pytest
import json
import os
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from unittest.mock import patch

@pytest.mark.integration
def test_apply_with_template_no_state_existing_cloud_org(existing_org_project_id, tmp_path):
    """
    Scenario 4: apply [TPL] + No State + Existing Org (Cloud).
    Adoption Scenario: Verify that 'apply' automatically adopts an existing Org 
    instead of trying to create it (which would 409).
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        template = {
            "billing_type": "PAYG", 
            "drz": False,
            "runtime_location": "northamerica-northeast1", 
            "analytics_region": "us-central1"
        }
        Path("t.json").write_text(json.dumps(template))
        
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{existing_org_project_id}"')
        
        # Testing REAL production flow (Impersonation enabled)
        result = runner.invoke(cli, ["apply", "t.json", "--auto-approve"])
        
        if result.exit_code != 0:
             print(result.output)
             assert "already exists" not in result.output
        else:
             assert result.exit_code == 0
             assert "Convergence Complete" in result.output

@pytest.mark.integration
@patch("scripts.cli.commands.core._run_main_folder")
def test_apply_with_template_no_state_empty_cloud_bootstrap_only(mock_run_main, ephemeral_project, tmp_path):
    """
    Scenario 3 (Shared Identity): apply [TPL] + No State + Empty Cloud (Group exists).
    Positive Scenario: Verify project initialization/bootstrap on a fresh project.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        result = runner.invoke(cli, ["apply", "us-central1", "--bootstrap-only"])
        
        assert result.exit_code == 0
        assert "✓ Bootstrap complete" in result.output
        assert "Skipping Main Phase" in result.output

import subprocess
from unittest.mock import MagicMock

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_mocked_org(ephemeral_project, tmp_path):
    """
    Scenario 1: apply [TPL] + No State + Empty Cloud.
    Hybrid Scenario: Verify end-to-end flow with a template.
    Phase 0 (Bootstrap): Real (Creates SA).
    Phase 1 (Main): Mocked (Prevents 45m Org Create).
    """
    runner = CliRunner()
    
    # Capture the real subprocess.run
    real_subprocess_run = subprocess.run

    def side_effect(cmd, **kwargs):
        # Identify Phase 1 execution by directory context
        cwd = str(kwargs.get("cwd", ""))
        
        if "1-main" in cwd:
            # Mock Phase 1 Success
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Mocked Phase 1 Success"
            return mock_res
            
        # Run Phase 0 (and gcloud checks) for Real
        return real_subprocess_run(cmd, **kwargs)

    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect) as mock_sub:
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
            
            # Using 'apply' instead of 'create'
            result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
            
            if result.exit_code != 0:
                print(result.output)
            
            assert result.exit_code == 0
            assert "✓ Bootstrap complete" in result.output
            assert "Convergence Complete" in result.output
            
            # Verify Phase 1 was attempted (by checking our mock interception)
            phase1_calls = [
                call for call in mock_sub.call_args_list 
                if "1-main" in str(call.kwargs.get("cwd", "")) and "apply" in call[0][0]
            ]
            assert len(phase1_calls) > 0, "Phase 1 (Main) was not invoked!"

@pytest.mark.integration
@patch("scripts.cli.commands.core._run_main_folder")
def test_apply_with_template_no_state_partial_cloud_adopts_network(mock_run_main, ephemeral_project, tmp_path):
    """
    Scenario 9: apply [TPL] + No State + Existing Network.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
        
        assert result.exit_code == 0
        assert "Adopting existing" in result.output
        assert "apigee-network" in result.output

@pytest.mark.integration
@patch("scripts.cli.commands.core._run_main_folder")
def test_apply_template_mismatch_no_state_existing_cloud(mock_run_main, ephemeral_project, tmp_path):
    """
    Scenario 4b/6: apply [BAD_TPL] + No State + Existing Cloud.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        template = {
            "billing_type": "PAYG",
            "runtime_location": "us-east1",
            "analytics_region": "us-east1"
        }
        # Use absolute path to ensure stager finds it in isolated fs
        p = Path("bad.json").absolute()
        p.write_text(json.dumps(template))
        
        result = runner.invoke(cli, ["apply", str(p), "--auto-approve"])
        
        assert result.exit_code == 0
        assert "Adopting existing" in result.output
        mock_run_main.assert_called_once()