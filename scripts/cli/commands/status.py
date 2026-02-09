import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from scripts.cli.config import ConfigLoader
from scripts.cli.commands.core import run_terraform
from scripts.cli.cloud.factory import get_cloud_provider

console = Console()

@click.command(name="status")
@click.option("--refresh", is_flag=True, help="Run 'terraform refresh' before showing status.")
@click.pass_context
def status_cmd(ctx, refresh):
    """Check environment status using Terraform state."""
    try:
        config = ConfigLoader.load(Path.cwd(), optional=True)
        project_id = config.project.gcp_project_id
    except Exception:
        project_id = None
            
    if not project_id:
        console.print("[red]Error: No project ID found. Run 'apim create' or 'apim import' first.[/red]")
        ctx.exit(1)

    if refresh:
        console.print(f"[dim]Refreshing state for {project_id}...[/dim]")
        exit_code = run_terraform(config, "refresh")
        if exit_code != 0:
            console.print("[yellow]Warning: Refresh failed. Showing cached state.[/yellow]")

    provider = get_cloud_provider()
    status = provider.get_status(project_id)
    
    if not status:
        console.print(f"[red]Error: Could not retrieve status for {project_id}. (State missing?)[/red]")
        ctx.exit(1)

    console.print(f"\n[bold underline]ENVIRONMENT STATUS: {project_id}[/bold underline]")
    
    # 1. Config Summary (Immutable)
    table = Table(show_header=False, box=None)
    table.add_row("[bold]Billing:[/bold]", status.config.billing_type)
    table.add_row("[bold]Sub Type:[/bold]", status.subscription_type)
    table.add_row("[bold]DRZ:[/bold]", "Yes" if status.is_drz else "No")
    
    if status.is_drz:
        table.add_row("[bold]Control Plane:[/bold]", status.config.control_plane_location)
        table.add_row("[bold]Consumer Region:[/bold]", status.config.consumer_data_region)
    else:
        table.add_row("[bold]Analytics Region:[/bold]", status.config.analytics_region)
        
    table.add_row("[bold]Runtime Region:[/bold]", status.config.runtime_location)
    console.print(table)

    # 2. Operational State
    console.print("\n[bold]OPERATIONAL STATE:[/bold]")
    if status.environments:
        console.print(f"  [green]✓ Environments:[/green] [dim]{', '.join(status.environments)}[/dim]")
    else:
        console.print(f"  [yellow]! No Environments found.[/yellow]")

    if status.instances:
        console.print(f"  [green]✓ Instances:[/green] [dim]{', '.join(status.instances)}[/dim]")
    else:
        console.print(f"  [yellow]! No Instances found.[/yellow]")

    console.print(f"  [green]✓ SSL Status:[/green] {status.ssl_status}")
    console.print("")