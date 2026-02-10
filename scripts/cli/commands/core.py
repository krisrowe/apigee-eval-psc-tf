import json
import os
import click
import shutil
import subprocess
import time
import sys
from pathlib import Path
from typing import Optional, List, Tuple
from rich.console import Console
from rich.status import Status
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgConfig

console = Console()

def is_debug() -> bool:
    """Checks if debug logging is enabled."""
    return os.environ.get("LOG_LEVEL") == "DEBUG"

def _execute_command(cmd: List[str], cwd: Path, env: dict, label: str) -> subprocess.CompletedProcess:
    """
    Executes a command with a spinner.
    If LOG_LEVEL=DEBUG, streams output live.
    Otherwise, captures and only shows on error.
    """
    if is_debug():
        console.print(f"[dim]Executing: {' '.join(cmd)} in {cwd}[/dim]")
        return subprocess.run(cmd, cwd=cwd, env=env)

    with console.status(f"[bold blue]{label}...[/bold blue]") as status:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            console.print(f"[green]✓ {label} completed.[/green]")
        else:
            console.print(f"[red]✘ {label} failed.[/red]")
            if result.stdout:
                console.print(result.stdout)
            if result.stderr:
                console.print(result.stderr)
        
        return result

def _get_current_user_email() -> Optional[str]:
    """Retrieves the currently authenticated gcloud user email."""
    try:
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
    """Enables required bootloader APIs."""
    cmd = [
        "gcloud", "services", "enable",
        "cloudresourcemanager.googleapis.com",
        "serviceusage.googleapis.com", 
        "iam.googleapis.com",
        "cloudidentity.googleapis.com",
        "iamcredentials.googleapis.com",
        "--project", project_id
    ]
    
    label = "Enabling GCP Bootloader APIs"
    result = _execute_command(cmd, Path.cwd(), os.environ, label)
    
    if result.returncode == 0 and not is_debug():
        # ServiceUsage stabilization
        time.sleep(5)

def _wait_for_impersonation(sa_email: str, project_id: str):
    """Polls until impersonation access is verified."""
    start = time.time()
    # Increased timeout to 120s for slow environments (Argolis)
    timeout = 120
    label = f"Verifying impersonation access for {sa_email}"
    
    with console.status(f"[bold blue]{label}...[/bold blue]") as status:
        while time.time() - start < timeout:
            try:
                # Use --impersonate-service-account to verify the user role grant has propagated
                cmd = [
                    "gcloud", "auth", "print-access-token",
                    "--impersonate-service-account", sa_email,
                    "--project", project_id,
                    "--quiet"
                ]
                # We use subprocess.run directly here to avoid double-labeling in output
                subprocess.run(cmd, check=True, capture_output=True)
                console.print(f"[green]✓ {label} verified.[/green]")
                return
            except subprocess.CalledProcessError:
                # Retry every 5s to avoid spamming GCP and hitting rate limits during propagation
                time.sleep(5)
                
        console.print(f"[yellow]⚠ {label} timed out after {timeout}s. Proceeding anyway.[/yellow]")

def _run_bootstrap_folder(stager: TerraformStager, config, deletes_allowed: bool = False, fake_secret: bool = False) -> Tuple[Optional[str], bool]:
    """Run Phase 0: Identity Bootstrap."""
    console.print("\n[bold dim]Phase 0: Identity Setup[/bold dim]")
    
    bootstrap_staging = stager.stage_phase("0-bootstrap")
    terraform_bin = shutil.which("terraform")
    
    _execute_command([terraform_bin, "init", "-input=false"], bootstrap_staging, os.environ, "Initializing Bootstrap")
    
    apply_cmd = [
        terraform_bin, "apply", "-input=false", "-auto-approve", "-lock=false",
        f"-var=allow_deletes={str(deletes_allowed).lower()}",
        f"-var=fake_secret={str(fake_secret).lower()}"
    ]
    
    user_email = _get_current_user_email()
    if user_email:
        apply_cmd.append(f"-var=current_user_email={user_email}")
    
    env = os.environ.copy()
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id
    _ensure_meta_apis(config.project.gcp_project_id)

    result = _execute_command(apply_cmd, bootstrap_staging, env, "Provisioning Identity foundation")
    
    if result.returncode != 0:
        return None, False

    changes_made = "0 added, 0 changed, 0 destroyed" not in (result.stdout or "")
    if not changes_made and not is_debug():
        console.print("[dim]Identity is stable (no changes).[/dim]")

    out_result = subprocess.run(
        [terraform_bin, "output", "-raw", "service_account_email"], 
        cwd=bootstrap_staging, capture_output=True, text=True
    )
    
    if out_result.returncode != 0:
        console.print("[red]Failed to read service_account_email output.[/red]")
        return None, False
        
    sa_email = out_result.stdout.strip()
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
    """Orchestrate multi-phase execution."""
    stager = TerraformStager(config)
    terraform_bin = shutil.which("terraform")
    
    sa_email = None
    changes_made = False
    if not skip_impersonation:
        sa_email, changes_made = _run_bootstrap_folder(stager, config, deletes_allowed, fake_secret)
        if not sa_email:
            return 1
            
    if bootstrap_only:
        console.print("[yellow]Bootstrap only requested. Stopping.[/yellow]")
        return 0
    
    if sa_email:
        if changes_made:
            _wait_for_impersonation(sa_email, config.project.gcp_project_id)
        elif not is_debug():
            console.print("[dim]Handoff verified (cached).[/dim]")

    console.print(f"\n[bold dim]Phase 1: Infrastructure Setup[/bold dim]")
    args = []
    if command == "apply" and auto_approve:
        args.append("-auto-approve")
    if targets:
        for t in targets:
            args.extend(["-target", t])
            
    args.append(f"-var=fake_secret={str(fake_secret).lower()}")
    args.append(f"-var=allow_deletes={str(deletes_allowed).lower()}")
    
    env = os.environ.copy()
    if not skip_impersonation and sa_email:
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
    env["GOOGLE_CLOUD_QUOTA_PROJECT"] = config.project.gcp_project_id

    main_staging = stager.stage_phase("1-main", config_files=config_files)
    if vars_to_inject:
        stager.inject_vars(main_staging, vars_to_inject)

    _execute_command([terraform_bin, "init", "-input=false"], main_staging, env, "Initializing Infrastructure")
    
    label = "Analyzing cloud state" if command == "plan" else "Converging infrastructure"
    cmd = [terraform_bin, command, "-input=false", "-lock=false"] + args
    
    result = _execute_command(cmd, main_staging, env, label)
    
    if result.returncode == 0 and not is_debug() and result.stdout:
        for line in result.stdout.splitlines():
            if "Plan:" in line or "Apply complete!" in line:
                console.print(f"[bold green]Summary: {line.strip()}[/bold green]")

    return result.returncode

@click.command()
@click.pass_context
def plan(ctx):
    """Synthesize configuration and run 'terraform plan'."""
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        console.print("[bold blue]Intent Discovery (Plan Mode)[/bold blue]")
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
    """Converge: Reconciles cloud state with configuration."""
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
            console.print("[dim]No template provided. Extracting variables from state...[/dim]")
            vars_to_inject = stager.extract_vars_from_state()
            if not vars_to_inject:
                 console.print("[red]Error: No existing state found. Use 'apim import' or provide a template.[/red]")
                 ctx.exit(1)
            vars_to_inject["apigee_enabled"] = not skip_apigee

        identity = "ADC" if skip_impersonation else "ADC → SA"
        console.print(f"[bold blue]Convergence Loop (Identity: {identity})[/bold blue]")
        
        exit_code = run_terraform(
            config, "apply", vars_to_inject=vars_to_inject,
            auto_approve=auto_approve, fake_secret=fake_secret,
            deletes_allowed=deletes_allowed, skip_impersonation=skip_impersonation,
            bootstrap_only=bootstrap_only
        )
        if exit_code != 0:
            ctx.exit(exit_code)
        console.print("[bold green]✓ System Converged[/bold green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)