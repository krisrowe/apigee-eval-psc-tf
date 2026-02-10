import json
import pytest
import subprocess
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from unittest.mock import patch, MagicMock

# We avoid shared fixtures for subprocess mocking as it's sensitive to context.
# We implement the mock directly in tests that need it.

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_bootstrap_only(ephemeral_project, tmp_path):
    """
    Scenario 2: apply [TPL] + No State + Empty Cloud.
    Verify Phase 0 (Bootstrap) succeeds. No mocking needed as we stop early.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        result = runner.invoke(cli, ["apply", "us-central1", "--bootstrap-only"])
        assert result.exit_code == 0
        assert "Bootstrap only requested" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_mocked_org(ephemeral_project, tmp_path):
    """
    Scenario 1: apply [TPL] + No State + Empty Cloud.
    Proves full flow works (Bootstrap + Handoff + Main invocation).
    Uses mocking for speed.
    """
    runner = CliRunner()
    real_sub = subprocess.run

    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        # Intercept Phase 1 (Main)
        if "1-main" in cwd:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Mocked Phase 1 Success"
            return mock_res
        return real_sub(cmd, **kwargs)

    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
            result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
            
            assert result.exit_code == 0
            assert "✓ System Converged" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_partial_cloud_mock_collision(ephemeral_project, tmp_path):
    """
    Scenario 3/9: apply [TPL] + No State + Existing Network.
    Proves CLI bubbles up 409 Collision error correctly.
    """
    runner = CliRunner()
    real_sub = subprocess.run

    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        # Intercept Phase 1 and simulate Collision
        if "1-main" in cwd:
            msg = "Error: google_compute_network.apigee_network already exists"
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = msg
            mock_res.stderr = msg
            return mock_res
        return real_sub(cmd, **kwargs)

    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
            result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve"])
            
            assert result.exit_code != 0
            assert "already exists" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_empty_cloud_skip_apigee(ephemeral_project, tmp_path):
    """
    Scenario 1b: apply [TPL] --skip-apigee
    True End-to-End verification without Org creation.
    No subprocess mocking. Tests real IAM handoff and Network creation.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
        
        # This runs FOR REAL but skips the expensive bits via CLI flag
        result = runner.invoke(cli, ["apply", "us-central1", "--auto-approve", "--skip-apigee"])
        
        if result.exit_code != 0:
            print(result.output)
            
        assert result.exit_code == 0
        assert "✓ System Converged" in result.output

@pytest.mark.integration
def test_apply_with_template_no_state_existing_cloud_org(existing_org_project_id, tmp_path):
    """
    Scenario 4: apply [TPL] + No State + Existing Org (Cloud).
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        template = {"billing_type": "PAYG", "runtime_location": "us-central1", "analytics_region": "us-central1"}
        p = Path("t.json").absolute()
        p.write_text(json.dumps(template))
        (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{existing_org_project_id}"')
        
        result = runner.invoke(cli, ["apply", str(p), "--auto-approve"])
        assert result.exit_code != 0
        assert "already exists" in result.output
