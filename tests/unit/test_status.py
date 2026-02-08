import pytest
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli

def test_status_missing_config(tmp_path):
    """'apim status' should error if no config exists."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["status"])
        assert result.exit_code != 0
        assert "No project ID found" in result.output

def test_status_live_probing(cloud_provider, tmp_path):
    """'apim status' should probe cloud resources."""
    project_id = "test-project"
    cloud_provider.orgs[project_id] = {"name": project_id}
    cloud_provider.instances[project_id] = [{"name": "inst-1"}]
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("apigee.tfvars").write_text(f'gcp_project_id = "{project_id}"\n')
        
        result = runner.invoke(cli, ["status"])
        
        assert result.exit_code == 0
        assert "Apigee Organization found" in result.output
        assert "1 Instance(s) found" in result.output
        assert "inst-1" in result.output

def test_status_template_compliance_match(cloud_provider, tmp_path):
    """'apim status --template' should report matches."""
    project_id = "test-project"
    runner = CliRunner()
    template_path = tmp_path / "t.json"
    template_path.write_text('{"region": "us-east1"}')
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("apigee.tfvars").write_text(f'gcp_project_id = "{project_id}"\nregion = "us-east1"\n')
        
        result = runner.invoke(cli, ["status", "--template", str(template_path)])
        
        assert result.exit_code == 0
        assert "TEMPLATE COMPLIANCE" in result.output
        assert "region: us-east1 (Match)" in result.output

def test_status_template_compliance_mismatch(cloud_provider, tmp_path):
    """'apim status --template' should report mismatches."""
    project_id = "test-project"
    runner = CliRunner()
    template_path = tmp_path / "t.json"
    template_path.write_text('{"region": "us-west1"}')
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("apigee.tfvars").write_text(f'gcp_project_id = "{project_id}"\nregion = "us-east1"\n')
        
        result = runner.invoke(cli, ["status", "--template", str(template_path)])
        
        assert result.exit_code == 0
        assert "TEMPLATE COMPLIANCE" in result.output
        assert "region: us-east1 (Expected: us-west1)" in result.output
