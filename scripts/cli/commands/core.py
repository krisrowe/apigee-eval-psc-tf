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

console = Console()

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
    
    # FORCE Quota Project for ADC
    # This solves the "cloudidentity requires a quota project" error by forcing
    # the SDK to use the target project for quota, bypassing local gcloud config.
    env = os.environ.copy()
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    # 0. Pre-Flight: Ensure CRM/IAM APIs are enabled
    # Terraform cannot enable these itself if it can't read the project state (Catch-22).
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

def _ensure_meta_apis(project_id: str):
    """
    Enables Cloud Resource Manager and Service Usage APIs.
    These are the 'Bootloader' APIs required for Terraform to even start planning.
    Without CRM, TF can't read the project. Without ServiceUsage, TF can't enable other APIs.
    """
    console.print("[dim]Pre-Flight: Ensuring bootloader APIs (CRM, ServiceUsage, IAM) are enabled...[/dim]")
    # We use gcloud here because it uses the active creds (User ADC) most reliably.
    # This command is idempotent.
    cmd = [
        "gcloud", "services", "enable",
        "cloudresourcemanager.googleapis.com",
        "serviceusage.googleapis.com", 
        "iam.googleapis.com",
        "--project", project_id
    ]
    # Suppress output unless error
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Warn but don't crash - let Terraform try, maybe user lacks permission but APIs are on.
        console.print(f"[yellow]Warning: Failed to auto-enable bootloader APIs: {result.stderr.strip()}[/yellow]")
    else:
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
    config_files: List[str] = None,
    auto_approve: bool = False,
    fake_secret: bool = False,
    deletes_allowed: bool = False,
    skip_impersonation: bool = False,
    force_bootstrap: bool = False,
    targets: Optional[List[str]] = None,
) -> int:
    """
    Orchestrate multi-phase terraform run.
    """
    stager = TerraformStager(config)
    
    # Step 1: Bootstrap (Phase 0)
    sa_email = None
    if not skip_impersonation:
        # Phase 0 does NOT receive user configs (as per design - user prefs overlay Main only)
        sa_email = _run_bootstrap_folder(stager, config, deletes_allowed=deletes_allowed, fake_secret=fake_secret)
        if not sa_email:
            return 1
            
    # Step 2: Main (Phase 1)
    args = []
    if command == "apply" and auto_approve:
        args.append("-auto-approve")
        
    if targets:
        for t in targets:
            args.extend(["-target", t])
            
    # Pass variables
    args.append(f"-var=fake_secret={str(fake_secret).lower()}")
    args.append(f"-var=allow_deletes={str(deletes_allowed).lower()}")
    
    if skip_impersonation:
        # Run main as user (Phase 1 but without SA env var)
         console.print("\n[bold dim]Phase 1: Main Infrastructure (User Identity - Skip Impersonation)...[/bold dim]")
         main_staging = stager.stage_phase("1-main", config_files=config_files)
         subprocess.run(["terraform", "init", "-input=false"], cwd=main_staging, check=True)
         cmd = ["terraform", command, "-input=false", "-lock=false"] + args
         result = subprocess.run(cmd, cwd=main_staging)
         return result.returncode
    else:
        return _run_main_folder(stager, config, sa_email, command, args, config_files=config_files)


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
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval.")
@click.option("--fake-secret", is_flag=True, help="Create/maintain the test secret.")
@click.option("--deletes-allowed", is_flag=True, help="Remove deny policy (allow_deletes=true).")
@click.option("--skip-impersonation", is_flag=True, help="Use ADC directly (don't impersonate SA).")
@click.option("--bootstrap", "force_bootstrap", is_flag=True, help="Force IAM bootstrap (skip checks).")
@click.pass_context
def apply(ctx, auto_approve, fake_secret, deletes_allowed, skip_impersonation, force_bootstrap):
    """Synthesize configuration and run 'terraform apply'."""
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        
        identity = "ADC (direct)" if skip_impersonation else "ADC → SA (impersonated)"
        if force_bootstrap:
            identity = "ADC (bootstrap forced)"
            
        console.print(f"[bold blue]Running Terraform Apply as {identity}...[/bold blue]")
        
        exit_code = run_terraform(
            config,
            "apply",
            auto_approve=auto_approve,
            fake_secret=fake_secret,
            deletes_allowed=deletes_allowed,
            skip_impersonation=skip_impersonation,
            force_bootstrap=force_bootstrap,
        )
        if exit_code != 0:
            ctx.exit(exit_code)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)
