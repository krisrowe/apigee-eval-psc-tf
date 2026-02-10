import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from scripts.cli.core import get_project_paths, load_tfstate, load_vars
from scripts.cli.cloud.factory import get_cloud_provider

console = Console()

@click.command(name="show")
@click.option("--raw", is_flag=True, help="Show raw .tfvars content.")
@click.pass_context
def show_cmd(ctx, raw):
    """Show configuration and resource status for the local project."""
    # 1. Resolve Local Paths
    var_file, state_file = get_project_paths()
    
    if not var_file.exists():
        console.print(f"[red]Error: No local configuration file found in CWD.[/red]")
        ctx.exit(1)

    if raw:
        with open(var_file, 'r') as f:
            console.print(f.read())
        return

    # 2. Local Status
    state_disp = str(state_file)
    if state_file.exists():
        state_disp = state_disp.replace(str(Path.home()), "~")
    else:
        state_disp = "[yellow]NOT INITIALIZED[/yellow]"

    console.print(f"\n[bold underline]LOCAL PROJECT STATUS[/bold underline]")
    console.print(f"  [bold]Config:[/bold] {str(var_file)}")
    console.print(f"  [bold]State:[/bold]  {state_disp}")
    
    # 3. Project Configuration & Cloud Status
    vars_dict = load_vars()
    project_id = vars_dict.get('gcp_project_id', 'UNKNOWN')

    console.print(f"\n[bold blue]PROJECT: {project_id}[/bold blue]")

    if project_id != 'UNKNOWN':
        console.print(f"\n[bold]CLOUD STATUS (via Terraform State):[/bold]")
        provider = get_cloud_provider()
        status = provider.get_status(project_id)
        
        if status:
             table = Table(show_header=False, box=None)
             table.add_row("[bold]Billing:[/bold]", status.config.billing_type)
             table.add_row("[bold]DRZ:[/bold]", "Yes" if status.is_drz else "No")
             if status.is_drz:
                 table.add_row("[bold]CP:[/bold]", status.config.control_plane_location)
                 table.add_row("[bold]Data Region:[/bold]", status.config.consumer_data_region)
             
             table.add_row("[bold]Runtime Region:[/bold]", status.config.runtime_location)
             console.print(table)
             
             if status.environments:
                 console.print(f"    [green]✓ Environments:[/green] [dim]{', '.join(status.environments)}[/dim]")
             if status.instances:
                 console.print(f"    [green]✓ Instances:[/green] [dim]{', '.join(status.instances)}[/dim]")
             
             console.print(f"    [green]✓ SSL Status:[/green] {status.ssl_status}")
        else:
             console.print(f"    [yellow]! Could not retrieve status for {project_id}.[/yellow]")

    # 4. Tracked Resources (Raw Table)
    console.print(f"\n[bold]TRACKED RESOURCES (Terraform State):[/bold]")
    state = load_tfstate()
    if not state:
        console.print(f"    [yellow]Project not yet applied.[/yellow]")
    else:
        table = Table()
        table.add_column("Resource", style="cyan")
        table.add_column("Status", style="green")
        for res in state.get("resources", []):
            table.add_row(res.get("type", ""), "✓ found")
        console.print(table)
