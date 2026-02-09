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
        assert "Import Successful" in result.output
        assert Path("terraform.tfvars").exists()
        
        # Verify Bootstrap called
        boot.assert_called_once()
        
        # Verify Import Command
        args, _ = sub.call_args
        assert "import" in args[0]
        assert "organizations/proj-x" in args[0]

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
        # import subprocess should NOT be called
        sub.assert_not_called()

def test_import_fails_terraform_error(mock_import_deps, tmp_path):
    """Negative: Fails if terraform import command errors."""
    stager, boot, sub = mock_import_deps
    sub.return_value.returncode = 1 # Import command failed
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("t.json").write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["import", "p", "t.json"])
        assert result.exit_code == 1
        assert "Import Failed" in result.output
