import json
import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path
from unittest.mock import patch, MagicMock

VALID_TEMPLATE = {
    "billing_type": "EVALUATION",
    "drz": False,
    "runtime_location": "us-central1",
    "analytics_region": "us-central1"
}

@pytest.fixture
def mock_import_deps():
    with patch("scripts.cli.commands.import.TerraformStager") as stager, \
         patch("scripts.cli.commands.import._run_bootstrap_folder") as boot, \
         patch("subprocess.run") as sub:
        
        # Defaults for Success
        stager.return_value.resolve_template_path.side_effect = lambda x: Path(x).absolute()
        stager.return_value.stage_phase.return_value = Path("staged/1-main")
        boot.return_value = "sa@example.com"
        sub.return_value.returncode = 0
        # Mock stdout for state list checks
        sub.return_value.stdout = ""
        
        yield stager, boot, sub

# --- Positive Scenarios ---

def test_import_success(mock_import_deps, tmp_path):
    """Positive: Successful import flow."""
    stager, boot, sub = mock_import_deps
    runner = CliRunner()
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("t.json").write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["import", "proj-x", "t.json"])
        
        assert result.exit_code == 0
        assert "Import Discovery Complete" in result.output
        assert Path("terraform.tfvars").exists()
        
        # Verify Bootstrap called
        boot.assert_called_once()
        
        # Verify Subprocess was called multiple times (init + imports)
        assert sub.call_count >= 5

# --- Negative Scenarios ---

def test_import_fails_existing_config(mock_import_deps, tmp_path):
    """Negative: Fails if config exists."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text("exists")
        result = runner.invoke(cli, ["import", "p", "t"])
        assert result.exit_code != 0
        assert "already exists" in result.output

def test_import_fails_bootstrap(mock_import_deps, tmp_path):
    """Negative: Fails if bootstrap identity returns None/False."""
    stager, boot, sub = mock_import_deps
    boot.return_value = None # Bootstrap failed/cancelled
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("t.json").write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["import", "p", "t.json"])
        assert result.exit_code == 1
        # import subprocess SHOULD be called for Phase 0 (bootstrap imports) but NOT Phase 1
        # We can't easily assert not called for phase 1 here without deeper mocking, 
        # but exit code 1 is sufficient.

def test_import_resilient_to_terraform_error(mock_import_deps, tmp_path):
    """Positive: Resilience - Ignores import errors (assumes missing resource)."""
    stager, boot, sub = mock_import_deps
    sub.return_value.returncode = 1 # Import command failed
    sub.return_value.stderr = "Cannot import non-existent resource"
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("t.json").write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["import", "p", "t.json"])
        # Should now succeed with warnings instead of failing
        assert result.exit_code == 0
        assert "will try creation" in result.output or "Not found in cloud" in result.output