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
def init():
    """Scaffold a new project configuration in the current directory."""
    cwd = Path.cwd()
    config_path = cwd / "apigee.toml"
    
    if config_path.exists():
        console.print(f"[yellow]Warning: {config_path} already exists.[/yellow]")
        if not click.confirm("Overwrite?"):
            return

    console.print(f"[bold green]Initializing new Apigee project in {cwd}[/bold green]")
    
    name = Prompt.ask("Project Name", default=cwd.name)
    project_id = Prompt.ask("GCP Project ID")
    region = Prompt.ask("GCP Region", default="us-central1")
    domain = Prompt.ask("Domain Name (e.g. api.example.com)", default="")

    content = f"""[project]
name = "{name}"
gcp_project_id = "{project_id}"
region = "{region}"

[apigee]
billing_type = "PAYG"
analytics_region = "{region}"

[network]
domain = "{domain}"
"""
    with open(config_path, "w") as f:
        f.write(content)
    
    console.print(f"[bold green]✓ Created apigee.toml[/bold green]")
    console.print("You can now add Terraform files to ./infra/ or run 'apim plan'")

@cli.command()
@click.confirmation_option(prompt="Are you sure you want to clear the build cache?")
def clean():
    """Wipe the local build cache (XDG Cache)."""
    # This will be implemented fully when Engine is ready
    # For now, we just print what we would do
    console.print("[yellow]Cache clearing logic pending Engine implementation...[/yellow]")

# Register Core Commands
from scripts.cli.commands.core import plan, apply
cli.add_command(plan)
cli.add_command(apply)

# Register API Commands
from scripts.cli.commands.apis import apis
cli.add_command(apis)

if __name__ == "__main__":
    cli()
