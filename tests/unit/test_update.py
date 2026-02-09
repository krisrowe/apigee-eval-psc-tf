import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

@pytest.fixture
def mock_run_terraform():
    with patch("scripts.cli.commands.update.run_terraform") as m:
        m.return_value = 0
        yield m

# --- Positive Scenarios ---

@pytest.fixture
def mock_state_file(tmp_path):
    """Mocks the existence of a terraform state file with an org."""
    # Logic in update.py: stager.staging_dir / "states" / "1-main" / "terraform.tfstate"
    # We need to ensure ConfigLoader loads a config that points to our tmp_path or we mock TerraformStager.
    # update.py instantiates TerraformStager(config). 
    # We can patch TerraformStager to return a specific staging_dir.
    
    with patch("scripts.cli.commands.update.TerraformStager") as MockStager, \
         patch("scripts.cli.commands.update.subprocess.run") as mock_sub, \
         patch("scripts.cli.commands.update.shutil.which") as mock_which:
        
        mock_which.return_value = "/bin/terraform"
        
        stager = MockStager.return_value
        stager.staging_dir = tmp_path
        state_dir = tmp_path / "states" / "1-main"
        state_dir.mkdir(parents=True)
        
        def write_state(has_org=True):
            # Create a dummy file so exists() returns True
            (state_dir / "terraform.tfstate").write_text("{}")
            
            # Configure mock_sub to return valid JSON when 'show' is called
            # We match the structure expected by update.py
            if has_org:
                output = json.dumps({
                    "values": {
                        "root_module": {
                            "resources": [
                                {"type": "google_apigee_organization", "address": "google_apigee_organization.org"}
                            ]
                        }
                    }
                })
            else:
                 output = json.dumps({"values": {"root_module": {"resources": []}}})
            
            mock_sub.return_value.returncode = 0
            mock_sub.return_value.stdout = output
            
        write_state(True)
        yield write_state

def test_update_success(mock_run_terraform, mock_state_file, tmp_path):
    """
    Positive: 'apim update' runs if state contains org.
    Maps to Integration Scenario 1: Minimal Config (Project ID only).
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text('gcp_project_id="p"') 
        
        result = runner.invoke(cli, ["update"])
        
        assert result.exit_code == 0
        assert "Updating Apigee" in result.output
        mock_run_terraform.assert_called_once()

def test_update_auto_approve(mock_run_terraform, mock_state_file, tmp_path):
    """Positive: Passes auto-approve flag."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text('gcp_project_id="p"')
        
        result = runner.invoke(cli, ["update", "--auto-approve"])
        
        assert result.exit_code == 0
        kwargs = mock_run_terraform.call_args[1]
        assert kwargs.get("auto_approve") is True

def test_update_fails_no_state_org(mock_state_file, tmp_path):
    """Negative: Fails if Apigee Org not in state."""
    mock_state_file(has_org=False) # Write state without org
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text('gcp_project_id="p"')
        
        result = runner.invoke(cli, ["update"])
        
        assert result.exit_code == 1
        assert "No Apigee Organization found in local state" in result.output

def test_update_fails_no_config(tmp_path):
    """Negative: Fails if no configuration found."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["update"])
        assert result.exit_code != 0
        assert "Could not find configuration file" in result.output

def test_update_fails_terraform_error(mock_run_terraform, mock_state_file, tmp_path):
    """
    Negative: Fails if terraform returns error.
    Maps to Integration Scenario 3 (Conflicting Config) where TF returns non-zero exit code.
    """
    mock_run_terraform.return_value = 1
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text('gcp_project_id="p"')
        
        result = runner.invoke(cli, ["update"])
        assert result.exit_code == 1
        assert "Update Failed" in result.output

