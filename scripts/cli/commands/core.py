import json
import os
import click
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, List, Tuple
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig

console = Console()

def _get_current_user_email() -> Optional[str]:
    """Retrieves the currently authenticated gcloud user email."""
    try:
        # We use 'account' which is reliable for user credentials
        res = subprocess.run(
            ["gcloud", "config", "get-value", "account"], 
            capture_output=True, text=True, check=True
        )
        email = res.stdout.strip()
        if "@" in email:
            return email
    except Exception:
        pass
    return None

def _ensure_meta_apis(project_id: str):
    """
    Enables Cloud Resource Manager and Service Usage APIs.
    These are the 'Bootloader' APIs required for Terraform to even start planning.
    """
    console.print("[dim]Pre-Flight: Ensuring bootloader APIs (CRM, ServiceUsage, IAM) are enabled...[/dim]")
    cmd = [
        "gcloud", "services", "enable",
        "cloudresourcemanager.googleapis.com",
        "serviceusage.googleapis.com", 
        "iam.googleapis.com",
        "cloudidentity.googleapis.com",
        "iamcredentials.googleapis.com",
        "--project", project_id
    ]
    # Suppress output unless error
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[yellow]Warning: Failed to auto-enable bootloader APIs: {result.stderr.strip()}[/yellow]")
    else:
        # Initial propagation for ServiceUsage often needs a few seconds regardless of polling
        # We keep a short fixed sleep here because there is no easy "check" for API readiness other than trying and failing.
        console.print("[dim]Bootloader APIs enabled. Stabilizing (5s)...[/dim]")
        time.sleep(5)

def _wait_for_impersonation(sa_email: str, project_id: str):
    """
    Polls until the current user can successfully impersonate the target SA.
    Replaces blind sleeps with active verification.
    """
    console.print(f"[dim]Verifying impersonation access for {sa_email}...[/dim]")
    start = time.time()
    # Retry for up to 60 seconds
    while time.time() - start < 60:
        try:
            # Try to get a token via impersonation using gcloud
            # This mimics what the Terraform Provider will do
            cmd = [
                "gcloud", "auth", "print-access-token",
                "--impersonate-service-account", sa_email,
                "--project", project_id,
                "--quiet"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            console.print("[dim]✓ Impersonation verified. Handoff ready.[/dim]")
            return
        except subprocess.CalledProcessError:
            time.sleep(2)
            
    console.print("[yellow]Warning: Impersonation check timed out. Proceeding anyway (Terraform might fail).[/yellow]")

def _run_bootstrap_folder(stager: TerraformStager, config, deletes_allowed: bool = False, fake_secret: bool = False) -> Tuple[Optional[str], bool]:
    """
    Run 0-bootstrap folder.
    Returns: (Service Account Email, Changes Detected Bool)
    """
    console.print("\n[bold dim]Phase 0: Bootstrapping (User Identity)...[/bold dim]")
    
    # 1. Stage bootstrap
    bootstrap_staging = stager.stage_phase("0-bootstrap")
    terraform_bin = shutil.which("terraform")
    
    # 2. Init
    subprocess.run([terraform_bin, "init", "-input=false"], cwd=bootstrap_staging, check=True)
    
    # 3. Apply (User Identity / ADC)
    apply_cmd = [
        terraform_bin, "apply", 
        "-input=false", 
        "-auto-approve", 
        "-lock=false",
        f"-var=allow_deletes={str(deletes_allowed).lower()}",
        f"-var=fake_secret={str(fake_secret).lower()}"
    ]
    
    user_email = _get_current_user_email()
    if user_email:
        apply_cmd.append(f"-var=current_user_email={user_email}")
    
    env = os.environ.copy()
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    _ensure_meta_apis(config.project.gcp_project_id)

    console.print(f"[dim]Executing: {' '.join(apply_cmd)} in {bootstrap_staging}[/dim]")
    
    # Capture output to check for drift/changes
    result = subprocess.run(apply_cmd, cwd=bootstrap_staging, env=env, capture_output=True, text=True)
    
    if result.returncode != 0:
        console.print(result.stdout)
        console.print(result.stderr)
        console.print("[red]Phase 0 Bootstrap Failed.[/red]")
        return None, False

    # Check for No-Op
    changes_made = True
    if "0 added, 0 changed, 0 destroyed" in result.stdout:
        changes_made = False
        console.print("[dim]Phase 0: No changes detected. Identity is stable.[/dim]")
    else:
        # Print output so user knows what happened
        console.print(result.stdout)
        console.print("[dim]Phase 0: Changes detected. Identity updated.[/dim]")

    # 4. Get Output (SA Email)
    output_cmd = [terraform_bin, "output", "-raw", "service_account_email"]
    out_result = subprocess.run(output_cmd, cwd=bootstrap_staging, capture_output=True, text=True)
    
    if out_result.returncode != 0:
        console.print("[red]Failed to read service_account_email output from bootstrap.[/red]")
        return None, False
        
    sa_email = out_result.stdout.strip()
    console.print(f"[green]✓ Bootstrap complete. SA: {sa_email}[/green]")
    return sa_email, changes_made

def run_terraform(
    config,
    command: str,
    vars_to_inject: dict = None,
    config_files: List[str] = None,
    auto_approve: bool = False,
    fake_secret: bool = False,
    deletes_allowed: bool = False,
    skip_impersonation: bool = False,
    targets: Optional[List[str]] = None,
    bootstrap_only: bool = False,
) -> int:
    """
    Orchestrate multi-phase terraform run.
    """
    stager = TerraformStager(config)
    terraform_bin = shutil.which("terraform")
    
    # Step 1: Bootstrap (Phase 0)
    sa_email = None
    changes_made = False
    
    if not skip_impersonation:
        # Phase 0 does NOT receive user configs (overlay Main only)
        sa_email, changes_made = _run_bootstrap_folder(stager, config, deletes_allowed=deletes_allowed, fake_secret=fake_secret)
        if not sa_email:
            return 1
            
    if bootstrap_only:
        console.print("[yellow]Skipping Main Phase (bootstrap-only requested).[/yellow]")
        return 0
    
    if sa_email:
        if changes_made:
            # If changes were made, verify we can actually use the credential.
            _wait_for_impersonation(sa_email, config.project.gcp_project_id)
        else:
            # Optimization: If no changes, trust existing propagation (or quick verify if paranoid)
            # We skip verification for speed on stable environments.
            console.print("[dim]Identity stable. Skipping verification.[/dim]")

    # Step 2: Main (Phase 1)
    args = []
    if command == "apply" and auto_approve:
        args.append("-auto-approve")
        
    if targets:
        for t in targets:
            args.extend(["-target", t])
            
    # Pass internal variables
    args.append(f"-var=fake_secret={str(fake_secret).lower()}")
    args.append(f"-var=allow_deletes={str(deletes_allowed).lower()}")
    
    env = os.environ.copy()
    if not skip_impersonation and sa_email:
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
    
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    main_staging = stager.stage_phase("1-main", config_files=config_files)
    
    if vars_to_inject:
        stager.inject_vars(main_staging, vars_to_inject)

    subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)
    
    # 3. Final Execution
    cmd = [terraform_bin, command, "-input=false", "-lock=false"] + args
    result = subprocess.run(cmd, cwd=main_staging, env=env)
    
    return result.returncode

@click.command()
@click.pass_context
def plan(ctx):
    """Synthesize configuration and run 'terraform plan'."""
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        
        console.print("[bold blue]Running Terraform Plan (as ADC direct)...[/bold blue]")
        exit_code = run_terraform(config, "plan", skip_impersonation=True)
        if exit_code != 0:
            ctx.exit(exit_code)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)

@click.command()
@click.argument("template_name", required=False)
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval.")
@click.option("--fake-secret", is_flag=True, help="Create/maintain the test secret.")
@click.option("--deletes-allowed", is_flag=True, help="Remove deny policy (allow_deletes=true).")
@click.option("--skip-impersonation", is_flag=True, help="Use ADC directly (don't impersonate SA).")
@click.option("--skip-apigee", is_flag=True, help="Skip Apigee resource creation (Networking/IAM only).")
@click.option("--bootstrap-only", is_flag=True, help="Stop after IAM bootstrap (Fast Test mode).")
@click.pass_context
def apply(ctx, template_name, auto_approve, fake_secret, deletes_allowed, skip_impersonation, skip_apigee, bootstrap_only):
    """
    Converge: Reconciles cloud state with configuration.
    
    If TEMPLATE_NAME is provided, it asserts that configuration (Intent).
    Otherwise, it extracts configuration from existing state (Reality).
    """
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        stager = TerraformStager(config)
        
        vars_to_inject = {}
        
        if template_name:
            template_path = stager.resolve_template_path(template_name)
            console.print(f"[dim]Loading template: {template_path}...[/dim]")
            schema = ApigeeOrgConfig.from_json_file(str(template_path))
            vars_to_inject = {
                "apigee_billing_type": schema.billing_type,
                "apigee_runtime_location": schema.runtime_location,
                "apigee_analytics_region": schema.analytics_region,
                "control_plane_location": schema.control_plane_location or "",
                "consumer_data_region": schema.consumer_data_region or "",
                "apigee_enabled": not skip_apigee,
                "gcp_project_id": config.project.gcp_project_id
            }
        else:
            console.print("[dim]No template provided. Attempting to extract variables from state...[/dim]")
            vars_to_inject = stager.extract_vars_from_state()
            
            if not vars_to_inject:
                 console.print("[red]Error: No existing state found for this project.[/red]")
                 console.print("[yellow]For new projects, run: apim apply [TEMPLATE][/yellow]")
                 console.print("[yellow]For existing projects, run: apim import [PROJECT_ID][/yellow]")
                 ctx.exit(1)
            
            vars_to_inject["apigee_enabled"] = not skip_apigee

        identity = "ADC (direct)" if skip_impersonation else "ADC → SA (impersonated)"
            
        console.print(f"[bold blue]Running Convergence as {identity}...[/bold blue]")
        
        exit_code = run_terraform(
            config,
            "apply",
            vars_to_inject=vars_to_inject,
            auto_approve=auto_approve,
            fake_secret=fake_secret,
            deletes_allowed=deletes_allowed,
            skip_impersonation=skip_impersonation,
            bootstrap_only=bootstrap_only
        )
        if exit_code != 0:
            ctx.exit(exit_code)
            
        console.print("[green]✓ Convergence Complete[/green]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)