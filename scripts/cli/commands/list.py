import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from scripts.cli.mappers import map_state_to_status

console = Console()
STATE_ROOT = Path.home() / ".local" / "share" / "apigee-tf"

@click.command(name="list")
def list_cmd():
    """List all tracked Apigee projects (based on local state files)."""
    if not STATE_ROOT.exists():
        console.print("[yellow]No projects found (state directory missing).[/yellow]")
        return

    projects = []
    # Iterate over project directories
    for project_dir in STATE_ROOT.iterdir():
        if not project_dir.is_dir():
            continue
            
        # Check for 1-main state (primary status source)
        state_file = project_dir / "tf" / "1-main" / "terraform.tfstate"
        
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                status = map_state_to_status(state)
                projects.append(status)

            except Exception:
                # Skip corrupted files
                pass

    if not projects:
        console.print("[yellow]No tracked projects found.[/yellow]")
        return

    table = Table(title="Tracked Projects")
    table.add_column("Project ID", style="cyan")
    table.add_column("Billing", style="green")
    table.add_column("DRZ", style="blue")
    table.add_column("CP", style="blue")
    table.add_column("Cons. Data Region", style="yellow")
    table.add_column("Runtime Region", style="red")
    table.add_column("SSL", style="magenta")
    
    for p in sorted(projects, key=lambda x: x.project_id):
        table.add_row(
            p.project_id,
            p.config.billing_type,
            "Yes" if p.is_drz else "No",
            p.config.control_plane_location or "-",
            p.config.consumer_data_region or p.config.analytics_region or "-",
            p.config.runtime_location,
            p.ssl_status
        )

    console.print(table)