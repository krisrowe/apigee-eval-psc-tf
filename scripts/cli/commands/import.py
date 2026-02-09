import click
import shutil
import subprocess
import os
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgTemplate, SchemaValidationError
from scripts.cli.commands.core import _run_bootstrap_folder

console = Console()

@click.command(name="import")
@click.argument("project_id")
@click.argument("template_name")
@click.option("--force", is_flag=True, help="Overwrite local config if exists.")
@click.pass_context
def import_cmd(ctx, project_id, template_name, force):
    """
    Adoption: Imports existing Apigee Organization.
    """
    cwd = Path.cwd()
    tfvars_path = cwd / "terraform.tfvars"
    
    # 1. Check Config
    if tfvars_path.exists() and not force:
        console.print(f"[red]Error: {tfvars_path.name} already exists.[/red]")
        ctx.exit(1)
        
    # 2. Resolve & Validate Template
    try:
        dummy_config = ConfigLoader.load(cwd, optional=True) 
        stager = TerraformStager(dummy_config) 
        template_path = stager.resolve_template_path(template_name)
        
        console.print(f"[dim]Validating template: {template_path}...[/dim]")
        schema = ApigeeOrgTemplate.from_json_file(str(template_path))
        console.print("[green]✓ Template Verified[/green]")
    except Exception as e:
        console.print(f"[red]Template/Schema Error:[/red] {e}")
        ctx.exit(1)

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
        
        console.print("\n[bold dim]Phase 0: Bootstrapping Identity...[/bold dim]")
        sa_email = _run_bootstrap_folder(stager, config)
        if not sa_email:
            ctx.exit(1)
            
        console.print(f"\n[bold dim]Phase 1: Importing Organization ({project_id})...[/bold dim]")
        main_staging = stager.stage_phase("1-main")
        
        terraform_bin = shutil.which("terraform")
        subprocess.run([terraform_bin, "init", "-input=false"], cwd=main_staging, check=True)
        
        cmd = [
            terraform_bin, "import", "-input=false", "-lock=false", 
            "google_apigee_organization.org", 
            f"organizations/{project_id}"
        ]
        
        env = os.environ.copy()
        env["GOOGLE_IMPERSONATE_SERVICE_ACCOUNT"] = sa_email
        
        console.print(f"[dim]Executing: {' '.join(cmd)}[/dim]")
        result = subprocess.run(cmd, cwd=main_staging, env=env)
        
        if result.returncode == 0:
            console.print("[green]✓ Import Successful[/green]")
            console.print("Run 'apim update' to align remaining resources.")
        else:
            console.print("[red]Import Failed[/red]")
            ctx.exit(result.returncode)
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)
