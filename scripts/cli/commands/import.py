import click
import shutil
import subprocess
import os
import json
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig, SchemaValidationError
from scripts.cli.commands.core import _run_bootstrap_folder
from scripts.cli.core import api_request

console = Console()

@click.command(name="import")
@click.argument("project_id")
@click.argument("template_name", required=False)
@click.option("--force", is_flag=True, help="Overwrite local config if exists.")
@click.pass_context
def import_cmd(ctx, project_id, template_name, force):
    """
    Adoption: Imports existing Apigee Organization.
    
    If TEMPLATE_NAME is provided, config is generated from that template.
    Otherwise, the CLI attempts to discover configuration from the Cloud API.
    """
    cwd = Path.cwd()
    tfvars_path = cwd / "terraform.tfvars"
    
    # 1. Check Config
    if tfvars_path.exists() and not force:
        console.print(f"[red]Error: {tfvars_path.name} already exists.[/red]")
        ctx.exit(1)
        
    schema = None
    
    # 2. Resolve Config (Template vs Discovery)
    if template_name:
        try:
            dummy_config = ConfigLoader.load(cwd, optional=True) 
            stager = TerraformStager(dummy_config) 
            template_path = stager.resolve_template_path(template_name)
            
            console.print(f"[dim]Validating template: {template_path}...[/dim]")
            schema = ApigeeOrgConfig.from_json_file(str(template_path))
        except Exception as e:
            console.print(f"[red]Template Error:[/red] {e}")
            ctx.exit(1)
    else:
        # Discovery Mode
        console.print(f"[dim]Discovering configuration for {project_id}...[/dim]")
        # We assume standard global endpoint first, or infer from project?
        # api_request uses control_plane_location from load_vars(), which we don't have yet!
        # So api_request will hit global. If org is regional, it might 404.
        # We need to iterate regions or ask user? 
        # Or just try global, if 404, try common regions?
        
        # Let's try global first
        status, resp = api_request("GET", f"organizations/{project_id}")
        if status == 404 or status == 403:
             # Try probing regions? This is the chicken-egg problem.
             # For now, let's assume if it fails, we assume global failure.
             # Ideally we loop through ['us', 'ca', 'eu', 'au'] etc.
             
             # Fallback Loop
             found = False
             for cp in ["us", "ca", "eu", "au", "ap", "sa", "me"]:
                 # We hack the URL construction logic by temporarily injecting a var? 
                 # Or just construct URL manually here.
                 token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
                 url = f"https://{cp}-apigee.googleapis.com/v1/organizations/{project_id}"
                 import urllib.request
                 req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                 try:
                     with urllib.request.urlopen(req) as r:
                         resp = json.loads(r.read().decode())
                         status = 200
                         found = True
                         break
                 except:
                     continue
             
             if not found:
                 console.print(f"[red]Error: Could not find Apigee Org '{project_id}' in Global or common Regional control planes.[/red]")
                 ctx.exit(1)

        if status != 200:
             console.print(f"[red]API Error ({status}):[/red] {resp}")
             ctx.exit(1)
             
        # Map Response -> Schema
        # DRZ Detection
        consumer_loc = resp.get("apiConsumerDataLocation")
        is_drz = bool(consumer_loc)
        
        # Control Plane Inference (if we found it via loop, we know it)
        # Or re-infer from consumer_loc
        cp_loc = None
        if is_drz:
             if "northamerica" in consumer_loc: cp_loc = "ca"
             elif "europe" in consumer_loc: cp_loc = "eu"
             elif "australia" in consumer_loc: cp_loc = "au"
             else: cp_loc = "us" # Fallback

        # Need to find Runtime Region (Instance)
        instance_loc = "us-central1" # Fail-safe default
        try:
            status, inst_resp = api_request("GET", f"organizations/{project_id}/instances")
            
            # If our simple api_request failed (404/403) due to regional control plane, try the CP-aware URL
            if status != 200 and cp_loc:
                 token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
                 url = f"https://{cp_loc}-apigee.googleapis.com/v1/organizations/{project_id}/instances"
                 import urllib.request
                 req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                 try:
                     with urllib.request.urlopen(req) as r:
                         inst_resp = json.loads(r.read().decode())
                         status = 200
                 except:
                     pass

            if status == 200 and "instances" in inst_resp and len(inst_resp["instances"]) > 0:
                first_inst = inst_resp["instances"][0]
                instance_loc = first_inst.get("location", instance_loc)
                console.print(f"[dim]Detected Runtime Location: {instance_loc}[/dim]")
            else:
                console.print(f"[yellow]Warning: No instances found or API failed. Defaulting to {instance_loc}.[/yellow]")

        except Exception as e:
            console.print(f"[yellow]Warning: Could not detect instance location ({e}). Defaulting to {instance_loc}.[/yellow]")
        
        schema = ApigeeOrgConfig(
            billing_type=resp.get("billingType"),
            drz=is_drz,
            analytics_region=resp.get("analyticsRegion"),
            consumer_data_region=consumer_loc,
            control_plane_location=cp_loc,
            runtime_location=instance_loc
        )

    # 3. Write Config
    try:
        content = schema.to_tfvars(project_id)
        with open(tfvars_path, "w") as f:
            f.write(content)
        console.print(f"[green]✓ Generated {tfvars_path.name}[/green]")
    except Exception as e:
        console.print(f"[red]Write Error:[/red] {e}")
        ctx.exit(1)
        
    # 4. Bootstrap & Import
    try:
        config = ConfigLoader.load(cwd)
        stager = TerraformStager(config)
        terraform_bin = shutil.which("terraform")
        
        # Prepare Environment for Terraform (Quota Project)
        env = os.environ.copy()
        env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id
        
        console.print("\n[bold dim]Phase 0: Bootstrapping Identity...[/bold dim]")
        
        # 4a. Stage 0-bootstrap to enable imports
        bootstrap_staging = stager.stage_phase("0-bootstrap")
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=bootstrap_staging, check=True, env=env)
        
        # 4b. Import Service Account
        sa_id = f"projects/{project_id}/serviceAccounts/terraform-deployer@{project_id}.iam.gserviceaccount.com"
        console.print("[dim]Attempting adoption of Service Account...[/dim]")
        subprocess.run([
            terraform_bin, "import", "-input=false", "-lock=false",
            "google_service_account.deployer", sa_id
        ], cwd=bootstrap_staging, capture_output=True, env=env)

        # 4c. Import Deny Policy
        # ID Format: policies/cloudresourcemanager.googleapis.com%2Fprojects%2F<PROJECT_ID>%2Fdenypolicies%2Fprotect-deletes
        encoded_parent = f"cloudresourcemanager.googleapis.com%2Fprojects%2F{project_id}"
        policy_id = f"policies/{encoded_parent}%2Fdenypolicies%2Fprotect-deletes"
        console.print("[dim]Attempting adoption of Deny Policy...[/dim]")
        subprocess.run([
            terraform_bin, "import", "-input=false", "-lock=false", 
            "google_iam_deny_policy.protect_deletes[0]", policy_id
        ], cwd=bootstrap_staging, capture_output=True, env=env)

        # 4d. Import Admin Group
        try:
            # 1. Get Parent Org ID
            org_id_proc = subprocess.run([
                "gcloud", "projects", "describe", project_id,
                "--format=value(parent.id)"
            ], capture_output=True, text=True)
            org_id = org_id_proc.stdout.strip()
            
            if org_id:
                # 2. Get Domain (displayName)
                domain_proc = subprocess.run([
                    "gcloud", "organizations", "describe", org_id,
                    "--format=value(displayName)"
                ], capture_output=True, text=True)
                domain = domain_proc.stdout.strip()
                
                if domain:
                    group_email = f"apigee-admins@{domain}"
                    console.print(f"[dim]Attempting adoption of Admin Group ({group_email})...[/dim]")
                    
                    # 3. Lookup Group ID
                    group_id_proc = subprocess.run([
                        "gcloud", "identity", "groups", "describe", group_email,
                        "--project", project_id,
                        "--format=value(name)"
                    ], capture_output=True, text=True)
                    
                    group_id = group_id_proc.stdout.strip()
                    
                    # 4. Import
                    if group_id and group_id_proc.returncode == 0:
                        subprocess.run([
                            terraform_bin, "import", "-input=false", "-lock=false", 
                            "google_cloud_identity_group.apigee_admins", group_id
                        ], cwd=bootstrap_staging, capture_output=True, env=env)
        except Exception:
            pass

        # 4e. Run Apply
        sa_email = _run_bootstrap_folder(stager, config)
        if not sa_email:
            ctx.exit(1)
            
        # Helper for Phase 1 Imports
        def try_import(resource_addr, resource_id):
            console.print(f"[dim]  Checking {resource_addr}...[/dim]")
            # Check state first to avoid re-importing (which errors)
            state_check = subprocess.run(
                [terraform_bin, "state", "list", resource_addr],
                cwd=main_staging, capture_output=True, text=True, env=env
            )
            if resource_addr in state_check.stdout:
                console.print(f"[green]    Already in state.[/green]")
                return

            # Attempt Import
            proc = subprocess.run(
                [terraform_bin, "import", "-input=false", "-lock=false", resource_addr, resource_id],
                cwd=main_staging, capture_output=True, text=True, env=env
            )
            if proc.returncode == 0:
                console.print(f"[green]    Imported![/green]")
            else:
                # If failure is "resource doesn't exist", that's fine - we will create it later.
                if "Cannot import non-existent" in proc.stderr or "404" in proc.stderr:
                    console.print(f"[dim]    Not found in cloud (will be created).[/dim]")
                else:
                    # Generic error warning
                    console.print(f"[yellow]    Import skipped/failed (will try creation): {proc.stderr.splitlines()[0]}[/yellow]")

        console.print(f"\n[bold dim]Phase 1: Importing Resources ({project_id})...[/bold dim]")
        main_staging = stager.stage_phase("1-main")
        
        # Add impersonation for Phase 1
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
        
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)
        
        # 1. Organization (Critical)
        try_import("google_apigee_organization.apigee_org", f"organizations/{project_id}")
        
        # 2. Network (Often pre-exists)
        try_import("google_compute_network.apigee_network", f"projects/{project_id}/global/networks/apigee-network")
        
        # 3. Instance (Standard region or overrides)
        # Note: We guess "us-central1" (or var.apigee_runtime_location) based on our simplistic discovery.
        # Ideally we'd list instances to get the real name/location.
        # For now, we try the most likely name: "us-central1" in org "project_id"
        instance_loc = schema.runtime_location or "us-central1"
        try_import("google_apigee_instance.apigee_instance", f"organizations/{project_id}/instances/{instance_loc}")
        
        # 4. Environment (Standard "dev")
        try_import("google_apigee_environment.apigee_env[\"dev\"]", f"organizations/{project_id}/environments/dev")
        
        # 5. Environment Group (Standard "eval-group")
        try_import("google_apigee_envgroup.envgroup[\"eval-group\"]", f"organizations/{project_id}/envgroups/eval-group")

        console.print("[green]✓ Import Discovery Complete[/green]")
        console.print("Run 'apim update' to reconcile configuration.")
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)
