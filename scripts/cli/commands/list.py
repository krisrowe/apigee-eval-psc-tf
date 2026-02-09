import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()
STATE_ROOT = Path.home() / ".local" / "share" / "apigee-tf" / "states"

@click.command(name="list")
def list_cmd():
    """List all tracked Apigee projects (based on local state files)."""
    if not STATE_ROOT.exists():
        console.print("[yellow]No projects found (state directory missing).[/yellow]")
        return

    projects = []
    # Collect data
    for state_file in STATE_ROOT.glob("*.tfstate"):
        if state_file.name.endswith("-0-bootstrap.tfstate"):
            continue 
        
        project_data = {
            "id": state_file.stem,
            "billing": "[dim]-[/dim]",
            "sub_type": "[dim]-[/dim]",
            "runtime": "[dim]-[/dim]",
            "consumer_region": "[dim]-[/dim]", 
            "runtime_region": "[dim]-[/dim]"
        }

        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
                
            for res in state.get("resources", []):
                # Org Details
                if res.get("type") == "google_apigee_organization":
                    for inst in res.get("instances", []):
                        attrs = inst.get("attributes", {})
                        project_data["billing"] = attrs.get("billing_type", "UNKNOWN")
                        project_data["sub_type"] = attrs.get("subscription_type", "UNKNOWN")
                        project_data["runtime"] = attrs.get("runtime_type", "UNKNOWN")
                        # analytics_region is often empty for PAYG/Cloud? Use consumer_data_location
                        project_data["consumer_region"] = attrs.get("api_consumer_data_location") or attrs.get("analytics_region", "UNKNOWN")

                # Instance Details (Runtime Region)
                if res.get("type") == "google_apigee_instance":
                    for inst in res.get("instances", []):
                        attrs = inst.get("attributes", {})
                        # If multiple instances, just show first or count? Let's show first for now.
                        if project_data["runtime_region"] == "[dim]-[/dim]":
                            project_data["runtime_region"] = attrs.get("location", "UNKNOWN")

        except Exception as e:
            # If state file is corrupted or unreadable, just list it with errors
            pass
            
        projects.append(project_data)

    if not projects:
        console.print("[yellow]No tracked projects found.[/yellow]")
        return

    table = Table(title="Tracked Projects")
    table.add_column("Project ID", style="cyan")
    table.add_column("Billing", style="green")
    table.add_column("Sub Type", style="blue")
    table.add_column("Runtime", style="magenta")
    table.add_column("Cons. Region", style="yellow")
    table.add_column("Runtime Region", style="red")
    
    for p in sorted(projects, key=lambda x: x["id"]):
        table.add_row(
            p["id"],
            p["billing"],
            p["sub_type"],
            p["runtime"],
            p["consumer_region"],
            p["runtime_region"]
        )

    console.print(table)
