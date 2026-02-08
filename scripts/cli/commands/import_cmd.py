import click
import json
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path
from rich.console import Console
from scripts.cli.core import get_project_paths, load_vars, load_settings, ensure_dirs
from scripts.cli.cloud.factory import get_cloud_provider
from scripts.cli.template import load_template
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager

console = Console()

def _run_tf_import(ctx, stager, address, res_id, vars_map):
    """Run a single terraform import using CLI variables to avoid needing a .tfvars file yet."""
    terraform_bin = shutil.which("terraform")
    cmd = [terraform_bin, "import", "-input=false"]
    for k, v in vars_map.items():
        cmd.append(f"-var={k}={v}")
    
    # We must point to the state location explicitly since we are running in the staging dir
    _, state_file = get_project_paths()
    cmd.append(f"-state={state_file}")
    cmd.extend([address, res_id])

    try:
        subprocess.run(cmd, cwd=stager.staging_dir, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode()
        if "already exists" in stderr or "Conflict" in stderr:
            return True # Already in state is a success for us
        console.print(f"    [red]Failed to import {address}:[/red] {stderr}")
        return False

@click.command(name="import")
@click.option("--project", help="Target GCP Project ID")
@click.option("--label", help="Discover project by label (e.g. key=value)")
@click.option("--force", is_flag=True, help="Force overwrite of existing config.")
@click.pass_context
def import_cmd(ctx, project, label, force):
    """
    Unified Import. Probes GCP and synchronizes state BEFORE writing config.
    """
    if project and label:
        console.print("[red]Error: --project and --label are mutually exclusive.[/red]")
        ctx.exit(1)

    var_file, state_file = get_project_paths()
    existing_vars = load_vars()
    provider = get_cloud_provider()
    
    # 1. Resolve Project ID
    requested_project_id = project or existing_vars.get("gcp_project_id")

    if label:
        if "=" not in label:
            console.print("[red]Error: Label must be in key=value format.[/red]")
            ctx.exit(1)
        l_key, l_val = label.split("=", 1)
        console.print(f"Discovering project with label [bold]{label}[/bold]...")
        requested_project_id = provider.get_project_id_by_label(l_key, l_val)
        if not requested_project_id:
            console.print(f"[red]Error: No project found with label '{label}'.[/red]")
            ctx.exit(1)

    if not requested_project_id:
        console.print("[red]Error: Specify --project ID or --label discovery.[/red]")
        ctx.exit(1)
    if existing_vars.get("gcp_project_id") and existing_vars.get("gcp_project_id") != requested_project_id and not force:
        console.print(f"[red]Error: Already attached to '{existing_vars['gcp_project_id']}'. Use --force to switch.[/red]")
        ctx.exit(1)

    # 2. Probe Cloud
    console.print(f"Probing GCP Project: [bold]{requested_project_id}[/bold]...")
    provider = get_cloud_provider()
    org_data = provider.get_org(requested_project_id)
    
    if not org_data:
        console.print(f"[red]Error: Apigee Org not found or access denied.[/red]")
        ctx.exit(1)

    imports = [
        {"to": "google_apigee_organization.apigee_org", "id": f"organizations/{requested_project_id}"}
    ]

    # Detect Instances
    inst_resp = provider.list_instances(requested_project_id)
    for inst in inst_resp:
        imports.append({"to": "google_apigee_instance.apigee_instance", "id": f"organizations/{requested_project_id}/instances/{inst['name']}"})

    # 3. ATOMIC SYNC: Initialize and Import into STATE
    console.print(f"Synchronizing state [dim](before writing config)[/dim]...")
    ensure_dirs()
    
    # Prepare dummy config for stager (we just need the provider blocks)
    config = ConfigLoader.load(Path.cwd(), optional=True)
    stager = TerraformStager(config)
    stager.stage()
    
    # Init
    terraform_bin = shutil.which("terraform")
    subprocess.run([terraform_bin, "init", "-input=false"], cwd=stager.staging_dir, capture_output=True, check=True)

    # Run Imports
    import_vars = {"gcp_project_id": requested_project_id}
    success_count = 0
    for imp in imports:
        console.print(f"  Importing {imp['to']}...")
        if _run_tf_import(ctx, stager, imp['to'], imp['id'], import_vars):
            success_count += 1
    
    else:
        # Default to terraform.tfvars for new imports
        if var_file.name == "apigee.tfvars":
             # If it resolved to apigee.tfvars existing, keep it
             pass 
        else:
             # creating new file
             var_file = Path.cwd() / "terraform.tfvars"

    # 4. FINAL COMMIT: Write local config ONLY if we synced something
    if success_count > 0:
        with open(var_file, 'w') as f:
            f.write(f'gcp_project_id = "{requested_project_id}"\n')
            # Additional discovered logic could go here
        console.print(f"\n[green]✓ Successfully imported {success_count} resources and saved config to {var_file.name}[/green]")
    else:
        console.print("[red]Import failed. Local config NOT written.[/red]")
        ctx.exit(1)
