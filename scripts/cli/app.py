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
@click.confirmation_option(prompt="Are you sure you want to clear the build cache?")
def clean():
    """Wipe the local build cache (XDG Cache)."""
    # This will be implemented fully when Engine is ready
    # For now, we just print what we would do
    console.print("[yellow]Cache clearing logic pending Engine implementation...[/yellow]")

import importlib

# Register Core Commands
from scripts.cli.commands.core import plan
from scripts.cli.commands.create import create
from scripts.cli.commands.update import update

# Dynamic import for 'import.py' to avoid keyword collision
try:
    mod = importlib.import_module("scripts.cli.commands.import")
    import_cmd = mod.import_cmd
except ImportError as e:
    console.print(f"[red]Failed to load import command:[/red] {e}")
    # Define dummy to prevent crash if not found
    @click.command(name="import")
    def import_cmd():
        console.print("[red]Import command unavailable.[/red]")

from scripts.cli.commands.show import show_cmd
from scripts.cli.commands.status import status_cmd
from scripts.cli.commands.list import list_cmd

cli.add_command(create)
cli.add_command(update)
cli.add_command(import_cmd, name="import")
cli.add_command(plan)
cli.add_command(show_cmd, name="show")
cli.add_command(status_cmd, name="status")
cli.add_command(list_cmd, name="list")

# Register API Commands
from scripts.cli.commands.apis import apis
from scripts.cli.commands.tests import tests
cli.add_command(apis)
cli.add_command(tests)

if __name__ == "__main__":
    cli()
