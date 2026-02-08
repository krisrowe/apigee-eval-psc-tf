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

# IAM resources that must be bootstrapped without impersonation
IAM_BOOTSTRAP_TARGETS = [
    "google_service_account.deployer",
    "google_cloud_identity_group.apigee_admins",
    "google_cloud_identity_group_membership.deployer_in_admins",
    "google_project_iam_member.admin_group_owner",
    "google_project_service.cloudidentity",
    "google_project_service.crm",
    "google_project_service.serviceusage",
    "google_project_service.iam",
]


def _check_sa_exists_in_state(staging_dir: Path) -> bool:
    """Check if terraform-deployer SA exists in terraform state."""
    terraform_bin = shutil.which("terraform")
    if not terraform_bin:
        return False
    
    try:
        result = subprocess.run(
            [terraform_bin, "state", "list"],
            cwd=staging_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False  # No state or error = SA doesn't exist
        
        return "google_service_account.deployer" in result.stdout
    except Exception:
        return False


def _run_bootstrap(staging_dir: Path, config) -> bool:
    """Run targeted apply for IAM resources without impersonation."""
    console.print("[yellow]⚡ Bootstrap required: SA not in state[/yellow]")
    terraform_bin = shutil.which("terraform")

    # Phase 1: Enable Critical APIs (CRM, ServiceUsage, IAM, CloudIdentity)
    # This must happen FIRST to allow other resources to be refreshed/read
    console.print("[dim]Phase 1: Enabling critical APIs (ADC direct)...[/dim]")
    phase1_targets = [
        "-target=google_project_service.crm",
        "-target=google_project_service.serviceusage",
        "-target=google_project_service.iam",
        "-target=google_project_service.cloudidentity"
    ]
    cmd1 = [
        terraform_bin, "apply",
        "-input=false",
        "-auto-approve",
        "-var=skip_impersonation=true",
    ] + phase1_targets
    
    result1 = subprocess.run(cmd1, cwd=staging_dir)
    if result1.returncode != 0:
        console.print("[red]Bootstrap Phase 1 (APIs) failed. Will attempt Phase 2 anyway...[/red]")
        # We continue because maybe APIs are already enabled but state is messy
    
    # Phase 2: Create IAM Resources
    console.print("[dim]Phase 2: Creating IAM resources (ADC direct)...[/dim]")
    phase2_targets = []
    for target in IAM_BOOTSTRAP_TARGETS:
        if not target.startswith("google_project_service."):
            phase2_targets.extend(["-target", target])
            
    cmd2 = [
        terraform_bin, "apply",
        "-input=false",
        "-auto-approve",
        "-var=skip_impersonation=true",
    ] + phase2_targets
    
    result2 = subprocess.run(cmd2, cwd=staging_dir)
    if result2.returncode != 0:
        console.print("[red]Bootstrap Phase 2 (IAM) failed. Cannot proceed.[/red]")
        return False
    
    console.print("[green]✓ Bootstrap complete. APIs enabled and SA created.[/green]\n")
    return True


def run_terraform(
    config,
    command: str,
    auto_approve: bool = False,
    fake_secret: bool = False,
    deletes_allowed: bool = False,

    skip_impersonation: bool = False,
    force_bootstrap: bool = False,
    targets: Optional[List[str]] = None,
) -> int:
    """
    Run a terraform command with automatic bootstrap detection.
    
    - Checks if SA exists in state
    - If not, bootstraps IAM resources first (skip_impersonation=true)
    - Then runs the requested command
    """
    stager = TerraformStager(config)
    stager.stage()
    
    terraform_bin = shutil.which("terraform")
    if not terraform_bin:
        raise RuntimeError("'terraform' binary not found in PATH")
    
    # Initialize if needed
    if not (stager.staging_dir / ".terraform").exists():
        subprocess.run(
            [terraform_bin, "init", "-input=false"],
            cwd=stager.staging_dir,
            check=True
        )
    
    # Check if SA exists - if not, bootstrap first (unless we're already skipping impersonation)
    # OR if force_bootstrap is True
    should_bootstrap = force_bootstrap
    if not should_bootstrap and not skip_impersonation:
        should_bootstrap = not _check_sa_exists_in_state(stager.staging_dir)
        
    if should_bootstrap:
        if not _run_bootstrap(stager.staging_dir, config):
            return 1  # Bootstrap failed
    
    # Build command
    cmd = [terraform_bin, command, "-input=false"]
    if command == "apply":
        if auto_approve:
            cmd.append("-auto-approve")
        cmd.append("-lock=false")
    
    # Add targets if specified
    if targets:
        for target in targets:
            cmd.extend(["-target", target])
    
    # Add variables
    cmd.append(f"-var=skip_impersonation={str(skip_impersonation).lower()}")
    cmd.append(f"-var=fake_secret={str(fake_secret).lower()}")
    cmd.append(f"-var=allow_deletes={str(deletes_allowed).lower()}")
    
    # Run
    # DEBUG: Print command to verify variables
    console.print(f"[dim]DEBUG Executing: {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, cwd=stager.staging_dir)
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
