import click
from pathlib import Path
from dataclasses import asdict
from rich.console import Console
from rich.table import Table
from scripts.cli.config import ConfigLoader
from scripts.cli.engine import TerraformStager
from scripts.cli.schemas import ApigeeOrgTemplate
from scripts.cli.cloud.factory import get_cloud_provider

console = Console()

@click.command(name="status")
@click.option("--template", help="Optional template to compare against environment.")
@click.pass_context
def status_cmd(ctx, template):
    """Check cloud environment status and optional template compliance."""
    try:
        config = ConfigLoader.load(Path.cwd(), optional=True)
        project_id = config.project.gcp_project_id
    except Exception:
        project_id = None
            
    if not project_id:
        console.print("[red]Error: No project ID found. Run 'apim create' or 'apim import' first.[/red]")
        ctx.exit(1)

    console.print(f"\n[bold underline]ENVIRONMENT STATUS: {project_id}[/bold underline]")
    try:
        provider = get_cloud_provider()
        
        actual_state = {}
        
        # 1. Probe Organization
        org = provider.get_org(project_id)
        if org:
            actual_state["org"] = "exists"
            console.print(f"  [green]✓ Apigee Organization found.[/green]")
        else:
            actual_state["org"] = "missing"
            console.print(f"  [red]✗ Apigee Organization not found.[/red]")

        # 2. Probe Instances
        instances = provider.list_instances(project_id)
        actual_state["instances"] = [i['name'] for i in instances]
        if instances:
            console.print(f"  [green]✓ {len(instances)} Instance(s) found:[/green] [dim]{', '.join(actual_state['instances'])}[/dim]")
        else:
            console.print(f"  [yellow]! No Instances found.[/yellow]")

        # 3. Probe Environments
        envs = provider.get_environments(project_id)
        actual_state["environments"] = envs
        if envs:
            console.print(f"  [green]✓ {len(envs)} Environment(s) found:[/green] [dim]{', '.join(envs)}[/dim]")
        else:
            console.print(f"  [yellow]! No Environments found.[/yellow]")

        # 4. Networking (if applicable)
        domain = config.network.domain
        if domain:
            ssl = provider.get_ssl_certificate_status(project_id, domain)
            status = ssl.get("status", "UNKNOWN")
            actual_state["domain_name"] = domain
            actual_state["ssl_status"] = status
            console.print(f"  [green]✓ Domain Configed:[/green] {domain} [dim](SSL: {status})[/dim]")

        # 5. Template Compliance Check
        if template:
            try:
                stager = TerraformStager(config)
                template_path = stager.resolve_template_path(template)
                tmpl = ApigeeOrgTemplate.from_json_file(str(template_path))
                tmpl_data = asdict(tmpl)
                
                console.print(f"\n[bold underline]TEMPLATE COMPLIANCE: {template_path.name}[/bold underline]")
                
                # Mapping: Template Field -> Config Attribute
                # Note: Config object is nested (config.apigee.billing_type, config.project.region)
                # We need a helper to get actual values
                
                for key, expected in tmpl_data.items():
                    if expected is None: continue
                    if key == "drz": continue
                    
                    actual = None
                    if key == "billing_type":
                        actual = config.apigee.billing_type
                    elif key == "runtime_location":
                        actual = config.project.region # Mapped in ConfigLoader
                    elif key == "analytics_region":
                        actual = config.apigee.analytics_region
                    elif key == "control_plane_location":
                        actual = config.apigee.control_plane_location
                    elif key == "consumer_data_region":
                        actual = config.apigee.consumer_data_region
                    elif key == "instance_name":
                        actual = config.apigee.instance_name
                        
                    if actual == expected:
                         console.print(f"  [green]✓ {key}:[/green] {actual} (Match)")
                    else:
                         console.print(f"  [red]✗ {key}:[/red] {actual or '[missing]'} (Expected: {expected})")
                        
            except Exception as e:
                console.print(f"[red]Error performing compliance check:[/red] {e}")

    except Exception as e:
        console.print(f"[red]Error probing cloud:[/red] {e}")

    console.print("")
