import click
from pathlib import Path
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgTemplate, SchemaValidationError
from scripts.cli.commands.core import run_terraform

console = Console()

@click.command()
@click.argument("project_id")
@click.argument("template_name")
@click.option("--force", is_flag=True, help="Overwrite existing configuration.")
@click.pass_context
def create(ctx, project_id, template_name, force):
    """
    Greenfield Creation: Initializes and deploys a new Apigee organization.
    
    Args:
        project_id: The GCP Project ID.
        template_name: Name of the template (e.g., 'ca-drz' or 'path/to/file.json').
    """
    cwd = Path.cwd()
    tfvars_path = cwd / "terraform.tfvars"
    
    # 1. Check for Existing Config
    if tfvars_path.exists() and not force:
        console.print(f"[red]Error: {tfvars_path.name} already exists.[/red]")
        console.print("Use --force to overwrite, or 'apim update' to manage existing installation.")
        ctx.exit(1)

    # 2. Resolve & Validate Template
    try:
        # Instantiate stager with DUMMY config just to use resolver
        dummy_config = ConfigLoader.load(cwd, optional=True) 
        stager = TerraformStager(dummy_config) 
        template_path = stager.resolve_template_path(template_name)
        
        console.print(f"[dim]Validating template: {template_path}...[/dim]")
        schema = ApigeeOrgTemplate.from_json_file(str(template_path))
        console.print("[green]✓ Template Verified[/green]")
        
    except FileNotFoundError as e:
        console.print(f"[red]Template Not Found:[/red] {e}")
        ctx.exit(1)
    except SchemaValidationError as e:
        console.print(f"[red]Schema Validation Failed:[/red] {e}")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]Error processing template:[/red] {e}")
        ctx.exit(1)

    # 3. Write terraform.tfvars
    try:
        content = schema.to_tfvars(project_id)
        with open(tfvars_path, "w") as f:
            f.write(content)
        console.print(f"[green]✓ Generated {tfvars_path.name}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to write tfvars:[/red] {e}")
        ctx.exit(1)
        
    # 4. Initialize .gitignore
    gitignore_path = cwd / ".gitignore"
    if not gitignore_path.exists():
        with open(gitignore_path, "w") as f:
            f.write("terraform.tfvars\n")
    else:
        current = gitignore_path.read_text()
        if "terraform.tfvars" not in current:
            with open(gitignore_path, "a") as f:
                f.write("\nterraform.tfvars\n")

    # 5. Run Terraform Apply
    try:
        # Reload valid config now that tfvars exists
        config = ConfigLoader.load(ConfigLoader.find_root())
        
        console.print(f"[bold blue]Deploying Apigee to {project_id}...[/bold blue]")
        exit_code = run_terraform(config, "apply", auto_approve=False) # Interactive for Create
        
        if exit_code != 0:
            console.print("[red]Creation Failed.[/red]")
            ctx.exit(exit_code)
            
        console.print("[green]✓ Creation Complete[/green]")
            
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)
