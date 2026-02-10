import click
from pathlib import Path
from rich.console import Console
from scripts.cli.paths import get_state_path
import hcl2

console = Console()

@click.group(invoke_without_command=True)
@click.pass_context
def project(ctx):
    """
    Manage the active Google Cloud Project context.
    If no subcommand is provided, behaves like 'get'.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(project_get)

@project.command(name="get")
def project_get():
    """Show the currently configured project ID."""
    tfvars_path = Path.cwd() / "terraform.tfvars"
    
    if not tfvars_path.exists():
        console.print("[yellow]No project configured (terraform.tfvars missing).[/yellow]")
        return

    try:
        with open(tfvars_path, "r") as f:
            data = hcl2.load(f)
            current = data.get("gcp_project_id")
            if current:
                # hcl2 returns list for keys
                val = current[0] if isinstance(current, list) else current
                console.print(f"Current Project: [bold cyan]{val}[/bold cyan]")
            else:
                console.print("[yellow]terraform.tfvars exists but 'gcp_project_id' is missing.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error reading config:[/red] {e}")

@project.command(name="set")
@click.argument("project_id")
@click.option("--force", is_flag=True, help="Overwrite existing project ID if set.")
def project_set(project_id, force):
    """Set the active project ID for the current directory."""
    tfvars_path = Path.cwd() / "terraform.tfvars"
    
    if tfvars_path.exists():
        content = tfvars_path.read_text()
        if "gcp_project_id" in content and not force:
            # Check if it's the same
            if f'"{project_id}"' in content or f"'{project_id}'" in content:
                 console.print(f"[dim]Project already set to {project_id}[/dim]")
            else:
                console.print(f"[yellow]Warning: Project already configured.[/yellow]")
                console.print(f"Use [bold]--force[/bold] to overwrite.")
                return
        
        if force or "gcp_project_id" not in content:
            # Update logic
            lines = [line for line in content.splitlines() if "gcp_project_id" not in line]
            lines.insert(0, f'gcp_project_id = "{project_id}"')
            new_content = "\n".join(lines) + "\n"
            tfvars_path.write_text(new_content)
            console.print(f"[green]✓ Switched to project: {project_id}[/green]")
    else:
        # Create new
        content = f'gcp_project_id = "{project_id}"\n'
        tfvars_path.write_text(content)
        console.print(f"[green]✓ Initialized project: {project_id}[/green]")

    # Context Awareness / Advisory
    state_path = get_state_path(project_id, phase="1-main")
    if state_path.exists():
        console.print(f"[dim]Local state found at: {state_path}[/dim]")
        console.print(f"Recommended Next Steps:")
        console.print(f"  1. [bold]apim show[/bold]   - View current status and tracked resources.")
        console.print(f"  2. [bold]apim import[/bold] - (Optional) Refresh/Expand adoption if cloud state has drifted.")
        console.print(f"  3. [bold]apim apply[/bold]  - Converge infrastructure to desired state.")
    else:
        console.print("[yellow]No local state found for this project.[/yellow]")
        console.print(f"Recommended Next Steps:")
        console.print(f"  1. [bold]apim import[/bold] - Adopt existing resources (Recommended for brownfield).")
        console.print(f"  2. [bold]apim apply[/bold]  - Provision new infrastructure (Greenfield).")