import click
import shutil
import subprocess
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager

console = Console()

def _run_terraform(ctx, command, cwd):
    """Helper to run terraform commands with rich output."""
    terraform_bin = shutil.which("terraform")
    if not terraform_bin:
        console.print("[red]Error: 'terraform' binary not found in PATH.[/red]")
        ctx.exit(1)

    try:
        # We use subprocess directly to stream output to user
        process = subprocess.run(
            [terraform_bin, command, "-input=false"],
            cwd=cwd,
            check=True
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Terraform {command} failed.[/red]")
        ctx.exit(e.returncode)

@click.command()
@click.pass_context
def plan(ctx):
    """Synthesize configuration and run 'terraform plan'."""
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        
        stager = TerraformStager(config)
        stager.stage()
        
        # Initialize if needed (simple check for .terraform existence)
        if not (stager.staging_dir / ".terraform").exists():
            console.print("[dim]Initializing Terraform backend...[/dim]")
            _run_terraform(ctx, "init", stager.staging_dir)

        console.print("[bold blue]Running Terraform Plan...[/bold blue]")
        _run_terraform(ctx, "plan", stager.staging_dir)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)

@click.command()
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval.")
@click.pass_context
def apply(ctx, auto_approve):
    """Synthesize configuration and run 'terraform apply'."""
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        
        stager = TerraformStager(config)
        stager.stage()
        
        # Initialize if needed
        if not (stager.staging_dir / ".terraform").exists():
             _run_terraform(ctx, "init", stager.staging_dir)

        console.print("[bold blue]Running Terraform Apply...[/bold blue]")
        
        cmd = ["apply"]
        if auto_approve:
            cmd.append("-auto-approve")
            
        # For apply, we construct the command slightly differently to handle arguments
        terraform_bin = shutil.which("terraform")
        subprocess.run(
            [terraform_bin] + cmd,
            cwd=stager.staging_dir,
            check=True
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        ctx.exit(1)
