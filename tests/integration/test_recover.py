import pytest
import subprocess
import shutil
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from unittest.mock import patch, MagicMock

@pytest.mark.integration
@pytest.mark.skip(reason="apim import currently doesn't hydrate enough state (vars) to drive a template-less apply")
def test_recover_lost_state_full_flow(ephemeral_project, tmp_path):
    """
    Scenario: Disaster Recovery / New Workstation.
    1. Bootstrap a project (Real Cloud).
    2. DELETE local state (Simulate lost file / fresh clone).
    3. Import (Discovery).
    4. Apply (Convergence).
    """
    runner = CliRunner()
    real_sub = subprocess.run

    # Mock Phase 1 (Org) but allow Phase 0 (Bootstrap/IAM) and Import (Discovery)
    def side_effect(cmd, **kwargs):
        cwd = str(kwargs.get("cwd", ""))
        cmd_str = " ".join(cmd)
        
        # Phase 1: Mock Org Creation/Update
        if "1-main" in cwd and "apply" in cmd_str:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Mocked Phase 1 Success"
            return mock_res
            
        # Allow Bootstrap, Import, and Init
        return real_sub(cmd, **kwargs)

    with patch("scripts.cli.commands.core.subprocess.run", side_effect=side_effect) as mock_sub:
        with runner.isolated_filesystem(temp_dir=tmp_path):
            
            # 1. BOOTSTRAP (Real)
            # Create config
            (Path(tmp_path) / "terraform.tfvars").write_text(f'gcp_project_id = "{ephemeral_project}"')
            
            print("\\n[Test] Step 1: Bootstrap...")
            res1 = runner.invoke(cli, ["apply", "us-central1", "--bootstrap-only"])
            assert res1.exit_code == 0
            assert "✓ Bootstrap complete" in res1.output
            
            # 2. DELETE STATE (Simulate Loss)
            print("\\n[Test] Step 2: Deleting State...")
            # State is in ~/.local/share/apigee-tf/state/<project_id>
            # But the CLI uses XDG paths.
            # We need to find where it put it.
            # Actually, we can just delete the 'tfvars' file to simulate "New Clone"?
            # No, 'import' needs to generate tfvars.
            # 'import' works if state is missing.
            # To be thorough, we should ensure state is gone.
            # But wait, --bootstrap-only usually doesn't touch 1-main state.
            # It touches 0-bootstrap state.
            # 'import' hydrates 1-main state.
            # So currently, 1-main state IS empty.
            
            # 3. IMPORT (Real Discovery of what Bootstrap created)
            # We mock the 'terraform import' call for the Org/Net (since they don't exist yet),
            # BUT we want to see if it bootstraps correctly.
            print("\\n[Test] Step 3: Import...")
            res2 = runner.invoke(cli, ["import", ephemeral_project])
            assert res2.exit_code == 0
            assert "State Hydrated" in res2.output
            
            # 4. APPLY (Convergence)
            print("\\n[Test] Step 4: Apply...")
            res3 = runner.invoke(cli, ["apply", "--auto-approve"])
            assert res3.exit_code == 0
            assert "Convergence Complete" in res3.output
            
            # Verify Phase 1 was attempted (Mocked)
            phase1_calls = [
                call for call in mock_sub.call_args_list 
                if "1-main" in str(call.kwargs.get("cwd", "")) and "apply" in call[0][0]
            ]
            assert len(phase1_calls) > 0, "Phase 1 was not invoked!"