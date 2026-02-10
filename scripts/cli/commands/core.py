import json
import os
import click
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig

console = Console()

def _adopt_main_resources(project_id: str, terraform_bin: str, cwd: Path, env: dict):
    """
    Blind adoption of critical resources.
    """
    def try_import(resource_addr, resource_id):
        # 1. Check state
        state_check = subprocess.run(
            [terraform_bin, "state", "list", resource_addr],
            cwd=cwd, capture_output=True, text=True, env=env
        )
        if resource_addr in state_check.stdout:
            return

        # 2. Attempt Import
        subprocess.run(
            [terraform_bin, "import", "-input=false", "-lock=false", resource_addr, resource_id],
            cwd=cwd, capture_output=True, env=env
        )

    try_import("google_apigee_organization.apigee_org", f"organizations/{project_id}")
    try_import("google_compute_network.apigee_network", f"projects/{project_id}/global/networks/apigee-network")

def _run_bootstrap_folder(stager: TerraformStager, config, deletes_allowed: bool = False, fake_secret: bool = False) -> Optional[str]:
    """
    Run 0-bootstrap folder.
    Returns: Service Account Email if successful, None otherwise.
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
    
    # Pass current user email if available (for explicit TokenCreator grant)
    user_email = _get_current_user_email()
    if user_email:
        apply_cmd.append(f"-var=current_user_email={user_email}")
    
    # FORCE Quota Project for ADC
    env = os.environ.copy()
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    # 0. Pre-Flight: Ensure CRM/IAM APIs are enabled
    _ensure_meta_apis(config.project.gcp_project_id)

    console.print(f"[dim]Executing: {' '.join(apply_cmd)} in {bootstrap_staging}[/dim]")
    result = subprocess.run(apply_cmd, cwd=bootstrap_staging, env=env)
    
    if result.returncode != 0:
        console.print("[red]Phase 0 Bootstrap Failed.[/red]")
        return None

    # 4. Get Output (SA Email)
    output_cmd = [terraform_bin, "output", "-raw", "service_account_email"]
    out_result = subprocess.run(output_cmd, cwd=bootstrap_staging, capture_output=True, text=True)
    
    if out_result.returncode != 0:
        console.print("[red]Failed to read service_account_email output from bootstrap.[/red]")
        return None
        
    sa_email = out_result.stdout.strip()
    console.print(f"[green]✓ Bootstrap complete. SA: {sa_email}[/green]")
    return sa_email

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
    Without CRM, TF can't read the project. Without ServiceUsage, TF can't enable other APIs.
    """
    import time
    console.print("[dim]Pre-Flight: Ensuring bootloader APIs (CRM, ServiceUsage, IAM) are enabled...[/dim]")
    # We use gcloud here because it uses the active creds (User ADC) most reliably.
    # This command is idempotent.
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
        # Warn but don't crash - let Terraform try, maybe user lacks permission but APIs are on.
        console.print(f"[yellow]Warning: Failed to auto-enable bootloader APIs: {result.stderr.strip()}[/yellow]")
    else:
        # CRM API enablement takes time to propagate globally.
        # Without this pause, Terraform immediately fails with 403.
        console.print("[dim]Bootloader APIs enabled. Waiting 15s for propagation...[/dim]")
        time.sleep(15)
        console.print("[dim]Bootloader APIs verified.[/dim]")

def _run_main_folder(stager: TerraformStager, config, sa_email: str, command: str, args: List[str], config_files: List[str] = None) -> int:
    """
    Run 1-main folder.
    """
    console.print(f"\n[bold dim]Phase 1: Main Infrastructure (SA Identity: {sa_email})...[/bold dim]")
    
    # 1. Stage main (Injecting Configs if provided)
    main_staging = stager.stage_phase("1-main", config_files=config_files)
    
    terraform_bin = shutil.which("terraform")
    
    # 2. Init
    subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True)
    
    # 3. Apply/Plan (SA Identity)
    cmd = [terraform_bin, command, "-input=false", "-lock=false"] + args
    
    env = os.environ.copy()
    env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
    
    console.print(f"[dim]Executing: {' '.join(cmd)} in {main_staging}[/dim]")
    result = subprocess.run(cmd, cwd=main_staging, env=env)
    
    return result.returncode

def run_terraform(
    config,
    command: str,
    vars_to_inject: dict = None,
    config_files: List[str] = None,
    auto_approve: bool = False,
    fake_secret: bool = False,
    deletes_allowed: bool = False,
    skip_impersonation: bool = False,
    force_bootstrap: bool = False,
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
    if not skip_impersonation:
        # Phase 0 does NOT receive user configs (overlay Main only)
        sa_email = _run_bootstrap_folder(stager, config, deletes_allowed=deletes_allowed, fake_secret=fake_secret)
        if not sa_email:
            return 1
            
    if bootstrap_only:
        console.print("[yellow]Skipping Main Phase (bootstrap-only requested).[/yellow]")
        return 0

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
    
    # Environment Setup
    env = os.environ.copy()
    if not skip_impersonation and sa_email:
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
    
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    # Stage Main
    main_staging = stager.stage_phase("1-main", config_files=config_files)
    
    # Inject variables for this run
    if vars_to_inject:
        stager.inject_vars(main_staging, vars_to_inject)

    # Init
    subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True, env=env)
    
    # 2.5 Smart Adoption: Always try to import Org/Network before final apply
    _adopt_main_resources(config.project.gcp_project_id, terraform_bin, main_staging, env)

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
        # Plan always skips impersonation - it's read-only and doesn't validate permissions anyway
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
@click.option("--bootstrap", "force_bootstrap", is_flag=True, help="Force IAM bootstrap (skip checks).")
@click.option("--bootstrap-only", is_flag=True, help="Stop after IAM bootstrap (Fast Test mode).")
@click.pass_context
def apply(ctx, template_name, auto_approve, fake_secret, deletes_allowed, skip_impersonation, force_bootstrap, bootstrap_only):
    """
    Converge: Reconciles cloud state with configuration.
    
    If TEMPLATE_NAME is provided, it asserts that configuration (Intent).
    Otherwise, it extracts configuration from existing state (Reality).
    """
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        stager = TerraformStager(config)
        
        # 1. Resolve Variables
        vars_to_inject = {}
        
        if template_name:
            # Intent Mode: Use Template
            template_path = stager.resolve_template_path(template_name)
            console.print(f"[dim]Loading template: {template_path}...[/dim]")
            schema = ApigeeOrgConfig.from_json_file(str(template_path))
            # Build flat vars from schema
            vars_to_inject = {
                "apigee_billing_type": schema.billing_type,
                "apigee_runtime_location": schema.runtime_location,
                "apigee_analytics_region": schema.analytics_region,
                "control_plane_location": schema.control_plane_location or "",
                "consumer_data_region": schema.consumer_data_region or "",
                "gcp_project_id": config.project.gcp_project_id
            }
        else:
            # Maintenance Mode: Extract from State
            console.print("[dim]No template provided. Attempting to extract variables from state...[/dim]")
            vars_to_inject = stager.extract_vars_from_state()
            
            if not vars_to_inject:
                 console.print("[red]Error: No existing state found for this project.[/red]")
                 console.print("[yellow]For new projects, run: apim apply [TEMPLATE][/yellow]")
                 console.print("[yellow]For existing projects, run: apim import [PROJECT_ID][/yellow]")
                 ctx.exit(1)

        identity = "ADC (direct)" if skip_impersonation else "ADC → SA (impersonated)"
        if force_bootstrap:
            identity = "ADC (bootstrap forced)"
            
        console.print(f"[bold blue]Running Convergence as {identity}...[/bold blue]")
        
        exit_code = run_terraform(
            config,
            "apply",
            vars_to_inject=vars_to_inject,
            auto_approve=auto_approve,
            fake_secret=fake_secret,
            deletes_allowed=deletes_allowed,
            skip_impersonation=skip_impersonation,
            force_bootstrap=force_bootstrap,
            bootstrap_only=bootstrap_only
        )
        if exit_code != 0:
            ctx.exit(exit_code)
            
        console.print("[green]✓ Convergence Complete[/green]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)

