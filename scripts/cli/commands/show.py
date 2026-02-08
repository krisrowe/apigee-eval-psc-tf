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
    var_file, state_file = get_project_paths()
    
    if not var_file.exists():
        console.print(f"[red]Error: No local apigee.tfvars found in CWD.[/red]")
        ctx.exit(1)

    if raw:
        with open(var_file, 'r') as f:
            console.print(f.read())
        return

    vars_dict = load_vars()
    project_id = vars_dict.get('gcp_project_id')
    
    console.print(f"\n[bold underline]LOCAL PROJECT STATUS[/bold underline]")
    console.print(f"  [bold]Config:[/bold] {str(var_file)}")
    console.print(f"  [bold]State:[/bold]  {str(state_file) if state_file.exists() else '[yellow]NOT INITIALIZED[/yellow]'}")
    
    # Live Probing
    if project_id:
        console.print(f"\n[bold]CLOUD STATUS (Live API):[/bold]")
        provider = get_cloud_provider()
        org = provider.get_org(project_id)
        if org:
            console.print(f"    [green]✓ Apigee Organization found.[/green]")
            
            # Show Envs
            envs = provider.get_environments(project_id)
            if envs:
                console.print(f"    [dim]Environments: {', '.join(envs)}[/dim]")

            # DNS/SSL if nickname exists (default domain derivation uses nickname)
            nickname = vars_dict.get('project_nickname')
            if nickname:
                # DNS Zone Check
                ns = provider.get_dns_nameservers(project_id)
                if ns:
                    console.print(f"    [green]✓ DNS Zone found.[/green] [dim]Nameservers: {', '.join(ns[:2])}...[/dim]")
                
                # Derive hostname similar to main.tf logic
                # For now, we'll just check if it's likely configured
                domain = vars_dict.get('domain_name')
                if domain:
                    ssl = provider.get_ssl_certificate_status(project_id, domain)
                    status = ssl.get("status", "UNKNOWN")
                    console.print(f"    [green]✓ Domain:[/green] {domain} [dim](SSL: {status})[/dim]")

    # Tracked Resources
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
