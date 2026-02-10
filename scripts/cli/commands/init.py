import click
from pathlib import Path
from rich.console import Console

console = Console()

@click.command()
@click.argument("project_id")
@click.option("--force", is_flag=True, help="Overwrite existing project ID if set.")
def init(project_id, force):
    """
    Initialize the current directory with a project configuration.
    
    Creates or updates 'terraform.tfvars' with the specified GCP Project ID.
    """
    tfvars_path = Path.cwd() / "terraform.tfvars"
    
    if tfvars_path.exists():
        content = tfvars_path.read_text()
        if "gcp_project_id" in content and not force:
            console.print(f"[yellow]Warning: 'terraform.tfvars' already exists.[/yellow]")
            console.print(f"Use [bold]--force[/bold] to overwrite the project ID.")
            return

        # Simple update: Regex replace or append?
        # For robustness, if we are forcing, maybe we just rewrite/append?
        # Let's read, filter out existing ID line, and append new one.
        lines = [line for line in content.splitlines() if "gcp_project_id" not in line]
        lines.insert(0, f'gcp_project_id = "{project_id}"')
        new_content = "
".join(lines) + "
"
        
        tfvars_path.write_text(new_content)
        console.print(f"[green]✓ Updated {tfvars_path.name} with project ID: {project_id}[/green]")
        
    else:
        # Create new
        content = f'gcp_project_id = "{project_id}"
'
        tfvars_path.write_text(content)
        console.print(f"[green]✓ Created {tfvars_path.name} with project ID: {project_id}[/green]")
