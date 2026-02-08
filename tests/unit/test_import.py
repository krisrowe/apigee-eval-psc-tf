import os
import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_import_creates_vars_file_on_success(cloud_provider, monkeypatch, tmp_path):
    """
    Importing a valid project should create the local apigee.tfvars.
    """
    project_id = "test-project"
    cloud_provider.orgs[project_id] = {"name": project_id}
    cloud_provider.instances[project_id] = [{"name": "inst-1"}]
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        runner = CliRunner()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["import", "--project", project_id])
            
            assert result.exit_code == 0
            var_file = Path("apigee.tfvars")
            assert var_file.exists()
            assert f'gcp_project_id = "{project_id}"' in var_file.read_text()

def test_import_discovery_by_label_success(cloud_provider, monkeypatch, tmp_path):
    """
    'apim import --label key=val' should find the project and sync.
    """
    project_id = "ai-gateway-project"
    cloud_provider.project_labels[project_id] = {"app": "ai-gateway"}
    cloud_provider.orgs[project_id] = {"name": project_id}
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        runner = CliRunner()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["import", "--label", "app=ai-gateway"])
            
            assert result.exit_code == 0
            assert f"Discovering project with label app=ai-gateway..." in result.output
            assert Path("apigee.tfvars").exists()
            assert f'gcp_project_id = "{project_id}"' in Path("apigee.tfvars").read_text()

def test_import_fails_on_exclusive_args_violation(tmp_path):
    """
    Specifying both --project and --label should be an error.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["import", "--project", "p1", "--label", "k=v"])
    assert result.exit_code != 0
    assert "are mutually exclusive" in result.output

def test_import_fails_on_conflict_without_force(monkeypatch, tmp_path):
    """
    Importing a different project into an already-configured dir should fail without --force.
    """
    runner = CliRunner()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Dir already has project p1
        Path("apigee.tfvars").write_text('gcp_project_id = "p1"\n')
        
        # Try to import p2
        result = runner.invoke(cli, ["import", "--project", "p2"])
        
        assert result.exit_code != 0
        assert "Already attached to 'p1'" in result.output
        assert 'gcp_project_id = "p1"' in Path("apigee.tfvars").read_text()

def test_import_atomicity_on_cloud_failure(cloud_provider, monkeypatch, tmp_path):
    """
    If the cloud probe fails (org not found), no local config should be written.
    """
    project_id = "missing-project"
    # Org is NOT in cloud_provider.orgs
    
    runner = CliRunner()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["import", "--project", project_id])
        
        assert result.exit_code != 0
        assert "Apigee Org not found" in result.output
        assert not Path("apigee.tfvars").exists()
