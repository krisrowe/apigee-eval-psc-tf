import json
import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path
from unittest.mock import patch

# Mock Templates content for testing
VALID_TEMPLATE = {
    "billing_type": "EVALUATION",
    "drz": False,
    "runtime_location": "us-central1",
    "analytics_region": "us-central1"
}

@pytest.fixture
def mock_run_terraform():
    with patch("scripts.cli.commands.create.run_terraform") as m:
        m.return_value = 0
        yield m

@pytest.fixture
def mock_stager():
    with patch("scripts.cli.commands.create.TerraformStager") as m:
        instance = m.return_value
        instance.resolve_template_path.side_effect = lambda x: Path(x).absolute()
        yield instance

# --- Positive Scenarios ---

def test_create_success(mock_run_terraform, mock_stager, tmp_path):
    """Positive: 'apim create' generates tfvars and runs terraform."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        tmpl_path = Path("my-template.json")
        tmpl_path.write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["create", "my-project", "my-template.json"])
        
        assert result.exit_code == 0
        assert "Generated terraform.tfvars" in result.output
        assert "Creation Complete" in result.output
        
        tfvars = Path("terraform.tfvars").read_text()
        assert 'gcp_project_id = "my-project"' in tfvars

def test_create_force_overwrite(mock_run_terraform, mock_stager, tmp_path):
    """Positive: 'apim create --force' overwrites existing tfvars."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        tmpl_path = Path("t.json")
        tmpl_path.write_text(json.dumps(VALID_TEMPLATE))
        # MUST be valid HCL or ConfigLoader crashes before overwrite logic
        Path("terraform.tfvars").write_text('gcp_project_id="old"')
        
        result = runner.invoke(cli, ["create", "new-proj", "t.json", "--force"])
        
        assert result.exit_code == 0
        current = Path("terraform.tfvars").read_text()
        assert "old" not in current
        assert 'gcp_project_id = "new-proj"' in current

# --- Negative Scenarios ---

def test_create_fails_if_exists(tmp_path):
    """Negative: Fails if terraform.tfvars exists (no force)."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("terraform.tfvars").write_text("exists")
        result = runner.invoke(cli, ["create", "p", "t"])
        assert result.exit_code != 0
        assert "already exists" in result.output

def test_create_fails_invalid_template(mock_stager, tmp_path):
    """Negative: Fails if template validation fails."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Template missing required 'runtime_location'
        tmpl_path = Path("bad.json")
        tmpl_path.write_text(json.dumps({"drz": False})) 
        
        result = runner.invoke(cli, ["create", "p", "bad.json"])
        
        assert result.exit_code != 0
        assert "Schema Validation Failed" in result.output

def test_create_fails_terraform_error(mock_run_terraform, mock_stager, tmp_path):
    """Negative: Fails if terraform apply returns non-zero."""
    runner = CliRunner()
    mock_run_terraform.return_value = 1 # Terraform failed
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        tmpl_path = Path("t.json")
        tmpl_path.write_text(json.dumps(VALID_TEMPLATE))
        
        result = runner.invoke(cli, ["create", "p", "t.json"])
        assert result.exit_code == 1
        assert "Creation Failed" in result.output
