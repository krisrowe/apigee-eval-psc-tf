import click
import shutil
import subprocess
import os
import json
import time
import logging
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig
from scripts.cli.commands.core import _run_bootstrap_folder, wait_for_impersonation
from scripts.cli.core import api_request

logger = logging.getLogger(__name__)
console = Console()

@click.command(name="import")
@click.argument("project_id", required=False)
@click.option("--force", is_flag=True, help="Overwrite local config if exists.")
@click.option("--control-plane", help="Control Plane Location (e.g., 'ca', 'eu'). Required for DRZ orgs.")
@click.pass_context
def import_cmd(ctx, project_id, force, control_plane):
    """
    Adoption: Imports existing Apigee resources into Terraform state.
    
    If PROJECT_ID is omitted, it attempts to read 'gcp_project_id' from
    the local terraform.tfvars file.
    """
    cwd = Path.cwd()
    tfvars_path = cwd / "terraform.tfvars"
    
    logger.debug(f"Adoption startup. CWD: {cwd}")
    
    # 0. Resolve Project ID
    if not project_id:
        logger.debug("No Project ID provided. Probing local environment...")
        try:
            # Attempt to load from existing config using shared logic
            config = ConfigLoader.load(cwd, optional=True)
            if config:
                if config.project.gcp_project_id:
                    project_id = config.project.gcp_project_id
                    console.print(f"[dim]Using project ID from terraform.tfvars: {project_id}[/dim]")
                
                # Also try to load control_plane if not explicitly passed
                if not control_plane and config.apigee.control_plane_location:
                    control_plane = config.apigee.control_plane_location
                    console.print(f"[dim]Using control_plane from terraform.tfvars: {control_plane}[/dim]")
        except Exception as e:
            logger.debug(f"ConfigLoader failed during probe: {e}")
        
        if not project_id:
            console.print("[red]Error: Missing PROJECT_ID argument and could not find it in terraform.tfvars[/red]")
            console.print("Usage: apim import [PROJECT_ID]")
            ctx.exit(1)

    # 1. Discovery (Reality Check)
    console.print(f"[dim]Discovering existing resources for {project_id}...[/dim]")
    
    # Discovery via API to get IDs
    instance_loc = "us-central1"
    try:
        # Note: If this is DRZ, discovery via Global API might fail or return partial data.
        status, inst_resp = api_request("GET", f"organizations/{project_id}/instances")
        if status == 200 and "instances" in inst_resp and len(inst_resp["instances"]) > 0:
            instance_loc = inst_resp["instances"][0].get("location", instance_loc)
            logger.debug(f"Discovered instance location: {instance_loc}")
    except Exception as e:
        logger.debug(f"Discovery API failed: {e}")

    # 2. Write Config
    try:
        if not tfvars_path.exists() or force:
            content = [f'gcp_project_id = "{project_id}"']
            if control_plane:
                content.append(f'control_plane_location = "{control_plane}"')
                content.append('apigee_billing_type = "PAYG"') # DRZ implies PAYG usually
            
            with open(tfvars_path, "w") as f:
                f.write("\n".join(content) + "\n")
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
        dummy_vars = {
            "apigee_billing_type": "EVALUATION",
            "apigee_runtime_location": "us-central1",
            "apigee_analytics_region": "us-central1",
            "control_plane_location": control_plane or "",
            "domain_name": "example.com"
        }
        
        console.print("\n[bold dim]Phase 0: Hydrating Identity State...[/bold dim]")
        bootstrap_staging = stager.stage_phase("0-bootstrap")
        stager.inject_vars(bootstrap_staging, dummy_vars)
        
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=bootstrap_staging, check=True, env=env)
        
        # Imports (Phase 0)
        def try_import(staging_dir, resource_addr, resource_id):
            console.print(f"[dim]  Checking {resource_addr}...[/dim]")
            result = subprocess.run(
                [terraform_bin, "import", "-input=false", "-lock=false", "-no-color", resource_addr, resource_id],
                cwd=staging_dir, capture_output=True, env=env, text=True
            )
            if result.returncode == 0:
                console.print(f"[green]  + Imported {resource_addr}[/green]")
            elif "Resource already managed" in result.stderr:
                console.print(f"[dim]  . Already managed: {resource_addr}[/dim]")
            elif "Cannot import non-existent remote object" in result.stderr:
                console.print(f"[dim]  . Skipped (Not found in cloud): {resource_addr}[/dim]")
            else:
                console.print(f"[red]  - Import Failed: {result.stderr.strip()}[/red]")

        try_import(bootstrap_staging, "google_service_account.deployer", f"projects/{project_id}/serviceAccounts/terraform-deployer@{project_id}.iam.gserviceaccount.com")
        
        # Import Deny Policy (Phase 0)
        deny_policy_id = f"cloudresourcemanager.googleapis.com%2Fprojects%2F{project_id}/protect-deletes"
        try_import(bootstrap_staging, "google_iam_deny_policy.protect_deletes[0]", deny_policy_id)
        
        # Phase 0 Apply (Required to get SA email for Phase 1)
        sa_email, changes_made = _run_bootstrap_folder(stager, config)
        if not sa_email:
            ctx.exit(1)
            
        if changes_made:
            wait_for_impersonation(sa_email, project_id)
        else:
            console.print("[dim]Identity stable. Skipping verification.[/dim]")
            
        console.print(f"\n[bold dim]Phase 1: Hydrating Infrastructure State...[/bold dim]")
        main_staging = stager.stage_phase("1-main")
        stager.inject_vars(main_staging, dummy_vars)
        
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)
        
        # Imports (Phase 1)
        # Order: Instance -> Org -> Network -> APIs -> Attachments -> Ingress
        org_imported = False
        
        def try_import_with_status(staging_dir, resource_addr, resource_id):
            console.print(f"[dim]  Checking {resource_addr}...[/dim]")
            result = subprocess.run(
                [terraform_bin, "import", "-input=false", "-lock=false", "-no-color", resource_addr, resource_id],
                cwd=staging_dir, capture_output=True, env=env, text=True
            )
            if result.returncode == 0:
                console.print(f"[green]  + Imported {resource_addr}[/green]")
                return True
            elif "Resource already managed" in result.stderr:
                console.print(f"[dim]  . Already managed: {resource_addr}[/dim]")
                return True
            elif "Cannot import non-existent remote object" in result.stderr:
                console.print(f"[dim]  . Skipped (Not found in cloud): {resource_addr}[/dim]")
                return False
            else:
                console.print(f"[red]  - Import Failed: {result.stderr.strip()}[/red]")
                return False

        # 1. Base Infra
        try_import_with_status(main_staging, "google_apigee_instance.apigee_instance[0]", f"organizations/{project_id}/instances/{instance_loc}")
        if try_import_with_status(main_staging, "google_apigee_organization.apigee_org[0]", f"organizations/{project_id}"):
            org_imported = True
        try_import_with_status(main_staging, "google_compute_network.apigee_network", f"projects/{project_id}/global/networks/apigee-network")
        
        # 2. APIs
        apis = ["apigee", "compute", "servicenetworking", "cloudkms", "dns", "iam", "serviceusage", "crm", "secretmanager"]
        for api in apis:
            service_name = f"{api}.googleapis.com"
            if api == "crm": service_name = "cloudresourcemanager.googleapis.com"
            try_import_with_status(main_staging, f"google_project_service.{api}", f"{project_id}/{service_name}")

        # 3. Logical Apigee
        try_import_with_status(main_staging, "google_apigee_environment.apigee_env[\"dev\"]", f"organizations/{project_id}/environments/dev")
        try_import_with_status(main_staging, "google_apigee_envgroup.envgroup[\"eval-group\"]", f"organizations/{project_id}/envgroups/eval-group")
        
        # 4. Attachments (Dynamic Discovery)
        # EnvGroup Attachments
        try:
            status, resp = api_request("GET", f"organizations/{project_id}/envgroups/eval-group/attachments")
            logger.debug(f"EnvGroup Attachment discovery response: {resp}")
            if status == 200:
                # Handle plural or singular keys
                attachments = resp.get("environmentGroupAttachments") or resp.get("environmentGroupAttachment")
                if attachments:
                    for att in attachments:
                        att_id = att.get("name")
                        full_id = f"organizations/{project_id}/envgroups/eval-group/attachments/{att_id}"
                        logger.debug(f"Attempting import with ID: {full_id}")
                        try_import_with_status(main_staging, "google_apigee_envgroup_attachment.envgroup_attachment[\"eval-group-dev\"]", full_id)
        except Exception as e:
            logger.debug(f"EnvGroup Attachment discovery failed: {e}")

        # Instance Attachments
        try:
            status, resp = api_request("GET", f"organizations/{project_id}/instances/{instance_loc}/attachments")
            if status == 200 and "attachments" in resp:
                for att in resp["attachments"]:
                    att_name = att.get("name")
                    full_id = f"organizations/{project_id}/instances/{instance_loc}/attachments/{att_name}"
                    logger.debug(f"Attempting import with ID: {full_id}")
                    try_import_with_status(main_staging, "google_apigee_instance_attachment.instance_attachment[\"dev\"]", full_id)
        except Exception: pass
        
        # 5. Ingress (Module)
        try_import_with_status(main_staging, "module.ingress_lb[0].google_compute_global_address.lb_ip", f"projects/{project_id}/global/addresses/apigee-ingress-ip")
        try_import_with_status(main_staging, "module.ingress_lb[0].google_compute_health_check.lb_health_check", f"projects/{project_id}/global/healthChecks/apigee-ingress-health-check")
        try_import_with_status(main_staging, "module.ingress_lb[0].google_compute_region_network_endpoint_group.psc_neg", f"projects/{project_id}/regions/{instance_loc}/networkEndpointGroups/apigee-ingress-psc-neg")
        try_import_with_status(main_staging, "module.ingress_lb[0].google_compute_backend_service.lb_backend", f"projects/{project_id}/global/backendServices/apigee-ingress-backend")
        try_import_with_status(main_staging, "module.ingress_lb[0].google_compute_url_map.lb_url_map", f"projects/{project_id}/global/urlMaps/apigee-ingress-url-map")

        console.print("[green]✓ State Hydrated Successful[/green]")
        
        if not org_imported and not control_plane:
            console.print("\n[yellow]Warning: Apigee Organization was not found.[/yellow]")
            console.print("[yellow]If this is a Data Residency (DRZ) project (e.g. Canada, Europe), re-run with:[/yellow]")
            console.print(f"  [bold]apim import --control-plane=ca[/bold] (or eu, au, etc.)")
            
        console.print("Run 'apim apply' to reconcile configuration.")
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)
