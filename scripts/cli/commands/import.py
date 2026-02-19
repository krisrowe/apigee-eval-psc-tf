import click
import shutil
import subprocess
import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig
from scripts.cli.commands.core import _run_bootstrap_folder, wait_for_impersonation
from scripts.cli.core import api_request

logger = logging.getLogger(__name__)
console = Console()

def load_map_file(path: Path) -> List[Dict[str, str]]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load map {path}: {e}")
        return []

def get_phase(addr: str) -> str:
    """Determine phase based on resource type."""
    if addr.startswith("google_service_account") or addr.startswith("google_iam_deny_policy"):
        return "0-bootstrap"
    return "1-main"

def discover_context(project_id: str, instance_loc: str) -> Dict[str, str]:
    """Populate dynamic variables for ID resolution."""
    ctx = {
        "project_id": project_id,
        "instance_loc": instance_loc,
        "project_number": "",
        "semantic_cache_index_id": "",
        "semantic_cache_endpoint_id": ""
    }
    
    # 1. Project Number
    try:
        res = subprocess.run(
            ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
            capture_output=True, text=True, check=True
        )
        ctx["project_number"] = res.stdout.strip()
    except Exception as e:
        logger.debug(f"Failed to get project number: {e}")

    # 2. Vertex AI (AI Gateway) Discovery - Only if needed
    # We only check if we suspect AI Gateway usage, or just try lazily.
    # To keep it simple, let's try to find them.
    try:
        # Index
        res = subprocess.run(
            ["gcloud", "ai", "indexes", "list", 
             f"--project={project_id}", f"--region={instance_loc}", 
             "--filter=displayName:semantic-cache-index", "--format=value(name)"],
            capture_output=True, text=True
        )
        # name format: projects/.../locations/.../indexes/12345
        full_name = res.stdout.strip()
        if full_name:
            ctx["semantic_cache_index_id"] = full_name.split("/")[-1]

        # Endpoint
        res = subprocess.run(
            ["gcloud", "ai", "index-endpoints", "list", 
             f"--project={project_id}", f"--region={instance_loc}", 
             "--filter=displayName:semantic-cache-endpoint", "--format=value(name)"],
            capture_output=True, text=True
        )
        full_name = res.stdout.strip()
        if full_name:
            ctx["semantic_cache_endpoint_id"] = full_name.split("/")[-1]

    except Exception as e:
        logger.debug(f"AI Gateway discovery skipped/failed: {e}")
        
    return ctx

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
    package_root = Path(__file__).parent.parent.parent.parent.resolve() # apigee-tf root
    
    logger.debug(f"Adoption startup. CWD: {cwd}")
    
    # 0. Resolve Project ID
    if not project_id:
        logger.debug("No Project ID provided. Probing local environment...")
        try:
            config = ConfigLoader.load(cwd, optional=True)
            if config:
                if config.project.gcp_project_id:
                    project_id = config.project.gcp_project_id
                    console.print(f"[dim]Using project ID from terraform.tfvars: {project_id}[/dim]")
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
    
    instance_loc = "us-central1"
    try:
        status, inst_resp = api_request("GET", f"organizations/{project_id}/instances")
        if status == 200 and "instances" in inst_resp and len(inst_resp["instances"]) > 0:
            instance_loc = inst_resp["instances"][0].get("location", instance_loc)
            logger.debug(f"Discovered instance location: {instance_loc}")
    except Exception as e:
        logger.debug(f"Discovery API failed: {e}")

    # Build Context
    import_ctx = discover_context(project_id, instance_loc)

    # 2. Write Config
    try:
        if not tfvars_path.exists() or force:
            content = [f'gcp_project_id = "{project_id}"']
            if control_plane:
                content.append(f'control_plane_location = "{control_plane}"')
                content.append('apigee_billing_type = "PAYG"')
            
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
        
        env = os.environ.copy()
        env["GOOGLE_CLOUD_QUOTA_PROJECT"] = project_id
        
        dummy_vars = {
            "apigee_billing_type": "EVALUATION",
            "apigee_runtime_location": instance_loc,
            "apigee_analytics_region": "us-central1",
            "control_plane_location": control_plane or "",
            "domain_name": "example.com"
        }
        
        # Helper for execution
        def execute_import(staging_dir, addr, res_id):
            if not res_id or "{" in res_id: # Unresolved variable
                console.print(f"[dim]  . Skipped (Unresolved ID): {addr}[/dim]")
                return False

            console.print(f"[dim]  Checking {addr}...[/dim]")
            result = subprocess.run(
                [terraform_bin, "import", "-input=false", "-lock=false", "-no-color", addr, res_id],
                cwd=staging_dir, capture_output=True, env=env, text=True
            )
            if result.returncode == 0:
                console.print(f"[green]  + Imported {addr}[/green]")
                return True
            elif "Resource already managed" in result.stderr:
                console.print(f"[dim]  . Already managed: {addr}[/dim]")
                return True
            elif "Cannot import non-existent remote object" in result.stderr:
                console.print(f"[dim]  . Skipped (Not found in cloud): {addr}[/dim]")
                return False
            else:
                console.print(f"[red]  - Import Failed: {result.stderr.strip()}[/red]")
                return False

        # --- LOAD MAPS ---
        maps = []
        # Default Map
        default_map_path = package_root / "default.tfmap.json"
        if default_map_path.exists():
            maps.extend(load_map_file(default_map_path))
        
        # Local Maps
        for local_map in sorted(cwd.glob("*.tfmap.json")):
             maps.extend(load_map_file(local_map))

        # Split into phases
        phase0_items = [m for m in maps if get_phase(m["addr"]) == "0-bootstrap"]
        phase1_items = [m for m in maps if get_phase(m["addr"]) == "1-main"]

        # --- PHASE 0 ---
        console.print("\n[bold dim]Phase 0: Hydrating Identity State...[/bold dim]")
        bootstrap_staging = stager.stage_phase("0-bootstrap")
        stager.inject_vars(bootstrap_staging, dummy_vars)
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=bootstrap_staging, check=True, env=env)

        for item in phase0_items:
            try:
                resolved_id = item["id"].format(**import_ctx)
                execute_import(bootstrap_staging, item["addr"], resolved_id)
            except KeyError:
                 logger.warning(f"Skipping {item['addr']}: Missing context for {item['id']}")

        # Apply Phase 0
        sa_email, changes_made = _run_bootstrap_folder(stager, config)
        if not sa_email:
            ctx.exit(1)
        if changes_made:
            wait_for_impersonation(sa_email, project_id)
        else:
            console.print("[dim]Identity stable. Skipping verification.[/dim]")
            
        # --- PHASE 1 ---
        console.print(f"\n[bold dim]Phase 1: Hydrating Infrastructure State...[/bold dim]")
        main_staging = stager.stage_phase("1-main")
        stager.inject_vars(main_staging, dummy_vars)
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)

        org_imported = False
        for item in phase1_items:
            try:
                resolved_id = item["id"].format(**import_ctx)
                if execute_import(main_staging, item["addr"], resolved_id):
                    if item["addr"].startswith("google_apigee_organization"):
                        org_imported = True
            except KeyError:
                 logger.warning(f"Skipping {item['addr']}: Missing context for {item['id']}")

        # Legacy Dynamic Attachments (Hard to map declaratively due to API listing)
        # EnvGroup Attachments
        try:
            status, resp = api_request("GET", f"organizations/{project_id}/envgroups/eval-group/attachments")
            if status == 200:
                attachments = resp.get("environmentGroupAttachments") or resp.get("environmentGroupAttachment")
                if attachments:
                    for att in attachments:
                        att_id = att.get("name")
                        full_id = f"organizations/{project_id}/envgroups/eval-group/attachments/{att_id}"
                        execute_import(main_staging, "google_apigee_envgroup_attachment.envgroup_attachment[\"eval-group-dev\"]", full_id)
        except Exception: pass

        # Instance Attachments
        try:
            status, resp = api_request("GET", f"organizations/{project_id}/instances/{instance_loc}/attachments")
            if status == 200 and "attachments" in resp:
                for att in resp["attachments"]:
                    att_name = att.get("name")
                    full_id = f"organizations/{project_id}/instances/{instance_loc}/attachments/{att_name}"
                    execute_import(main_staging, "google_apigee_instance_attachment.instance_attachment[\"dev\"]", full_id)
        except Exception: pass

        console.print("[green]✓ State Hydrated Successful[/green]")
        
        if not org_imported and not control_plane:
            console.print("\n[yellow]Warning: Apigee Organization was not found.[/yellow]")
            
        console.print("Run 'apim apply' to reconcile configuration.")
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)