import click
import sys
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from scripts.cli.config import ConfigLoader

console = Console()

@click.group()
def cli():
    """Apigee Terraform Utility (Project-Centric Redesign)"""
    pass

@cli.command()
@click.option("--project", help="GCP Project ID for non-interactive identification.")
@click.option("--label", help="Discover project by label (e.g. key=value)")
@click.option("--force", is_flag=True, help="Force overwrite of existing configuration.")
@click.option("--template", help="Path to template for configuration defaults (excludes Project ID)")
def init(project, label, force, template):
    """Scaffold a new project configuration in the current directory."""
    from scripts.cli.template import load_template
    from scripts.cli.cloud.factory import get_cloud_provider
    cwd = Path.cwd()
    hcl_path = cwd / "apigee.tfvars"
    
    # 0. Mutual Exclusivity
    if project and label:
        console.print("[red]Error: --project and --label are mutually exclusive.[/red]")
        sys.exit(1)

    if hcl_path.exists() and not force:
        console.print(f"[yellow]Warning: {hcl_path.name} already exists.[/yellow]")
        if not click.confirm("Overwrite?"):
            return

    tmpl = {}
    if template:
        try:
            tmpl = load_template(template)
        except Exception as e:
            console.print(f"[red]Error loading template:[/red] {e}")
            sys.exit(1)

    # 1. Resolve Identity (Strictly from flags or Prompt)
    provider = get_cloud_provider()
    project_id = project
    
    if label:
        if "=" not in label:
            console.print("[red]Error: Label must be key=value[/red]")
            sys.exit(1)
        l_key, l_val = label.split("=", 1)
        project_id = provider.get_project_id_by_label(l_key, l_val)
        if not project_id:
            console.print(f"[red]Error: No project found with label '{label}'[/red]")
            sys.exit(1)
            
    # Interactive fallback if no Identity provided
    if not project_id:
        project_id = Prompt.ask("GCP Project ID")
        if not project_id:
            console.print("[red]Error: GCP Project ID is required.[/red]")
            sys.exit(1)

    # 2. Safety Check: If Org already exists, deny init (suggest import)
    try:
        if provider.get_org(project_id):
            console.print(f"[bold red]Stop:[/bold red] Apigee Organization already exists in [white]{project_id}[/white].")
            console.print(f"[yellow]To adopt this project, use:[/yellow] apim import --project {project_id}")
            sys.exit(1)
    except Exception:
        pass # Allow offline/permission errors to proceed to scaffolding

    # 3. Resolve Other Values
    region = tmpl.get("region", "us-central1")
    domain = tmpl.get("domain_name", "")

    # Only prompt for specifics if we didn't use an Identity flag
    if not project and not label:
        console.print(f"[bold green]Initializing new Apigee project in {cwd}[/bold green]")
        region = Prompt.ask("GCP Region", default=region)
        domain = Prompt.ask("Domain Name", default=domain)
    else:
        # Automated mode
        console.print(f"[bold green]Scaffolding configuration for {project_id}...[/bold green]")

    content = f"""# Apigee Project Identity (Required)
gcp_project_id   = "{project_id}"
region           = "{region}"

# Network Configuration
domain_name      = "{domain}"

# Apigee Configuration (Optional overrides)
# apigee_billing_type    = "PAYG" 
# control_plane_location = "us"
# state_suffix           = "dev"
"""
    with open(hcl_path, "w") as f:
        f.write(content)
    
    console.print(f"[bold green]✓ Created {hcl_path.name}[/bold green]")
    console.print("Add your *.tf files to this root and run 'apim plan'")

@cli.command()
@click.confirmation_option(prompt="Are you sure you want to clear the build cache?")
def clean():
    """Wipe the local build cache (XDG Cache)."""
    # This will be implemented fully when Engine is ready
    # For now, we just print what we would do
    console.print("[yellow]Cache clearing logic pending Engine implementation...[/yellow]")

# Register Core Commands
from scripts.cli.commands.core import plan, apply
from scripts.cli.commands.import_cmd import import_cmd
from scripts.cli.commands.show import show_cmd
from scripts.cli.commands.status import status_cmd

cli.add_command(plan)
cli.add_command(apply)
cli.add_command(import_cmd, name="import")
cli.add_command(show_cmd, name="show")
cli.add_command(status_cmd, name="status")

# Register API Commands
from scripts.cli.commands.apis import apis
from scripts.cli.commands.tests import tests
cli.add_command(apis)
cli.add_command(tests)

if __name__ == "__main__":
    cli()
