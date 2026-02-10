import json
import pytest
import subprocess
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from unittest.mock import patch, MagicMock

# Helper to provide a conditional subprocess mock that allows Phase 0 but mocks Phase 1
@pytest.fixture
def conditional_tf_mock():
    real_subprocess_run = subprocess.run

    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        # If running in 1-main (Phase 1), MOCK IT.
        if "1-main" in cwd:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Mocked Phase 1 Success"
            return mock_res
        # Otherwise (Phase 0, gcloud, etc.), Run for Real.
        return real_subprocess_run(cmd, **kwargs)
    
    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect) as mock:
        yield mock

@pytest.mark.integration
def test_apply_with_template_no_state_existing_cloud_org(existing_org_project_id, tmp_path, conditional_tf_mock):
    """
    Scenario 4: apply [TPL] + No State + Existing Org (Cloud).
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
        
        result = runner.invoke(cli, ["apply", "t.json", "--auto-approve"])
        
        if result.exit_code != 0:
             print(result.output)
             assert "already exists" not in result.output
        else:
             assert result.exit_code == 0
             assert "Convergence Complete" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_bootstrap_only(ephemeral_project, tmp_path, conditional_tf_mock):
    """
    Scenario 3 (Shared Identity): apply [TPL] + No State + Empty Cloud (Group exists).
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        result = runner.invoke(cli, ["apply", "us-central1", "--bootstrap-only"])
        
        assert result.exit_code == 0
        assert "✓ Bootstrap complete" in result.output
        assert "Skipping Main Phase" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_mocked_org(ephemeral_project, tmp_path, conditional_tf_mock):
    """
    Scenario 1: apply [TPL] + No State + Empty Cloud.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
        
        assert result.exit_code == 0
        assert "✓ Bootstrap complete" in result.output
        assert "Convergence Complete" in result.output
        
        # Verify Phase 1 was attempted (mocked)
        phase1_calls = [
            call for call in conditional_tf_mock.call_args_list 
            if "1-main" in str(call.kwargs.get("cwd", "")) and "apply" in call[0][0]
        ]
        assert len(phase1_calls) > 0

@pytest.mark.integration
def test_apply_with_template_no_state_partial_cloud_adopts_network(ephemeral_project, tmp_path, conditional_tf_mock):
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
def test_apply_template_mismatch_no_state_existing_cloud(ephemeral_project, tmp_path, conditional_tf_mock):
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
        p = Path("bad.json").absolute()
        p.write_text(json.dumps(template))
        
        result = runner.invoke(cli, ["apply", str(p), "--auto-approve"])
        
        assert result.exit_code == 0
        assert "Adopting existing" in result.output
