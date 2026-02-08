import os
import pytest
from click.testing import CliRunner
from scripts.cli.app import cli
from pathlib import Path

def test_init_scaffolds_flat_hcl_vars(cloud_provider, tmp_path):
    """
    'apim init' should create a flat apigee.tfvars based on user input.
    """
    runner = CliRunner()
    
    # Inputs: ProjectID, Region, Domain
    inputs = "my-project\nus-east1\napi.test.com\n"
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"], input=inputs)
        
        assert result.exit_code == 0
        assert "Created apigee.tfvars" in result.output
        
        var_file = Path("apigee.tfvars")
        assert var_file.exists()
        content = var_file.read_text()
        
        assert 'gcp_project_id   = "my-project"' in content
        assert 'region           = "us-east1"' in content
        assert 'domain_name      = "api.test.com"' in content
        assert '# apigee_billing_type' in content

def test_init_aborts_on_existing_config_without_overwrite(cloud_provider, tmp_path):
    """
    'apim init' should respect existing config and abort if user says 'n' to overwrite.
    """
    runner = CliRunner()
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create existing file
        Path("apigee.tfvars").write_text("existing")
        
        # Input: 'n' for overwrite prompt
        result = runner.invoke(cli, ["init"], input="n\n")
        
        assert "Warning: apigee.tfvars already exists." in result.output
        assert Path("apigee.tfvars").read_text() == "existing"

def test_init_with_project_is_non_interactive(cloud_provider, tmp_path):
    """
    'apim init --project' should skip all identity prompts and scaffold successfully.
    """
    runner = CliRunner()
    project_id = "automation-pid"
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--project", project_id])
        
        assert result.exit_code == 0
        assert f"Scaffolding configuration for {project_id}" in result.output
        content = Path("apigee.tfvars").read_text()
        assert f'gcp_project_id   = "{project_id}"' in content
        assert 'region           = "us-central1"' in content

def test_init_with_label_discovery(cloud_provider, tmp_path):
    """
    'apim init --label' should resolve project and scaffold without prompts.
    """
    project_id = "labeled-pid"
    cloud_provider.project_labels = {project_id: {"env": "prod"}}
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--label", "env=prod"])
        
        assert result.exit_code == 0
        assert f"Scaffolding configuration for {project_id}" in result.output
        assert f'gcp_project_id   = "{project_id}"' in Path("apigee.tfvars").read_text()

def test_init_with_label_not_found_errors(cloud_provider, tmp_path):
    """
    'apim init --label' should error if no project is found.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--label", "env=missing"])
        assert result.exit_code != 0
        assert "No project found with label" in result.output

def test_init_stops_if_org_exists(cloud_provider, tmp_path):
    """
    'apim init' should block scaffolding if an Org exists in cloud to prevent duplicate management.
    """
    project_id = "existing-org-project"
    cloud_provider.orgs[project_id] = {"name": project_id}
    
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--project", project_id])
        
        assert result.exit_code != 0
        assert "Stop: Apigee Organization already exists" in result.output
        assert "apim import --project" in result.output

def test_init_with_force_overwrites_existing_config(cloud_provider, tmp_path):
    """
    'apim init --force' should bypass prompts and overwrite existing config.
    """
    runner = CliRunner()
    inputs = "new-project\nus-central1\napi.new.com\n"
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("apigee.tfvars").write_text("existing")
        
        result = runner.invoke(cli, ["init", "--force"], input=inputs)
        
        assert result.exit_code == 0
        assert "Warning: apigee.tfvars already exists." not in result.output
        assert "existing" not in Path("apigee.tfvars").read_text()
        assert 'gcp_project_id   = "new-project"' in Path("apigee.tfvars").read_text()

def test_init_with_template_loads_defaults(cloud_provider, tmp_path):
    """
    'apim init --template' should use template values as prompt defaults.
    """
    runner = CliRunner()
    template_path = tmp_path / "tmpl.json"
    template_path.write_text('{"region": "tmpl-reg"}')
    
    # Inputs: explicit-pid, then Enter for region (accept template default), Enter for domain
    inputs = "explicit-pid\n\n\n" 
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--template", str(template_path)], input=inputs)
        
        assert result.exit_code == 0
        content = Path("apigee.tfvars").read_text()
        assert 'gcp_project_id   = "explicit-pid"' in content
        assert 'region           = "tmpl-reg"' in content

def test_init_with_template_but_no_project_prompts_for_id(cloud_provider, tmp_path):
    """
    Templates provide defaults for region/domain, but Project ID must still be prompted/provided.
    """
    runner = CliRunner()
    template_path = tmp_path / "t.json"
    template_path.write_text('{"region": "template-reg"}')
    
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Input: explicit-pid, then Enter for region (template default), Enter for domain
        result = runner.invoke(cli, ["init", "--template", str(template_path)], input="explicit-pid\n\n\n")
        
        assert result.exit_code == 0
        content = Path("apigee.tfvars").read_text()
        assert 'gcp_project_id   = "explicit-pid"' in content
        assert 'region           = "template-reg"' in content
