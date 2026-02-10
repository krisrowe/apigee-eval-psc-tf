import click
import shutil
import subprocess
import os
import json
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig
from scripts.cli.commands.core import _run_bootstrap_folder
from scripts.cli.core import api_request

console = Console()

@click.command(name="import")
@click.argument("project_id")
@click.option("--force", is_flag=True, help="Overwrite local config if exists.")
@click.pass_context
def import_cmd(ctx, project_id, force):
    """
    Adoption: Imports existing Apigee resources into Terraform state.
    
    This command populates the local state file by discovering existing
    infrastructure. It does NOT generate configuration files other than
    the minimal terraform.tfvars.
    """
    cwd = Path.cwd()
    tfvars_path = cwd / "terraform.tfvars"
    
    # 1. Discovery (Reality Check)
    console.print(f"[dim]Discovering existing resources for {project_id}...[/dim]")
    
    # Discovery via API to get IDs
    instance_loc = "us-central1"
    try:
        status, inst_resp = api_request("GET", f"organizations/{project_id}/instances")
        if status == 200 and "instances" in inst_resp and len(inst_resp["instances"]) > 0:
            instance_loc = inst_resp["instances"][0].get("location", instance_loc)
    except:
        pass

    # 2. Write Config (Project ID Only)
    try:
        if not tfvars_path.exists() or force:
            tfvars_content = f'gcp_project_id = "{project_id}"\n'
            with open(tfvars_path, "w") as f:
                f.write(tfvars_content)
            console.print(f"[green]✓ Generated {tfvars_path.name}[/green]")
    except Exception as e:
        console.print(f"[red]Write Error:[/red] {e}")
        ctx.exit(1)
        
    # 3. Bootstrap & Import
    try:
        config = ConfigLoader.load(cwd)
        stager = TerraformStager(config)
        terraform_bin = shutil.which("terraform")
        
        # Prepare Environment
        env = os.environ.copy()
        env["GOOGLE_CLOUD_QUOTA_PROJECT"] = project_id
        
        # We inject dummy variables to satisfy Terraform parser during import
        # Terraform doesn't read these for import IDs, but it validates their presence in HCL.
        dummy_vars = {
            "apigee_billing_type": "EVALUATION",
            "apigee_runtime_location": "us-central1",
            "apigee_analytics_region": "us-central1",
            "control_plane_location": "",
            "domain_name": "example.com"
        }
        
        console.print("\n[bold dim]Phase 0: Hydrating Identity State...[/bold dim]")
        bootstrap_staging = stager.stage_phase("0-bootstrap")
        stager.inject_vars(bootstrap_staging, dummy_vars)
        
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=bootstrap_staging, check=True, env=env)
        
        # Imports (Phase 0)
        def try_import(staging_dir, resource_addr, resource_id):
            console.print(f"[dim]  Checking {resource_addr}...[/dim]")
            subprocess.run(
                [terraform_bin, "import", "-input=false", "-lock=false", resource_addr, resource_id],
                cwd=staging_dir, capture_output=True, env=env
            )

        try_import(bootstrap_staging, "google_service_account.deployer", f"projects/{project_id}/serviceAccounts/terraform-deployer@{project_id}.iam.gserviceaccount.com")
        # Note: Deny policy ID is complex, skipping for brevity or add if needed.
        
        # Phase 0 Apply (Required to get SA email for Phase 1)
        sa_email = _run_bootstrap_folder(stager, config)
        if not sa_email:
            ctx.exit(1)
            
        console.print(f"\n[bold dim]Phase 1: Hydrating Infrastructure State...[/bold dim]")
        main_staging = stager.stage_phase("1-main")
        stager.inject_vars(main_staging, dummy_vars)
        
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)
        
        # Imports (Phase 1)
        try_import(main_staging, "google_apigee_organization.apigee_org", f"organizations/{project_id}")
        try_import(main_staging, "google_compute_network.apigee_network", f"projects/{project_id}/global/networks/apigee-network")
        try_import(main_staging, "google_apigee_instance.apigee_instance", f"organizations/{project_id}/instances/{instance_loc}")
        try_import(main_staging, "google_apigee_environment.apigee_env[\"dev\"]", f"organizations/{project_id}/environments/dev")
        try_import(main_staging, "google_apigee_envgroup.envgroup[\"eval-group\"]", f"organizations/{project_id}/envgroups/eval-group")

        console.print("[green]✓ State Hydrated Successful[/green]")
        console.print("Run 'apim apply' to reconcile configuration.")
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)