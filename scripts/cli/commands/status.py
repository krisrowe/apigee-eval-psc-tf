import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from scripts.cli.core import load_vars
from scripts.cli.cloud.factory import get_cloud_provider
from scripts.cli.template import load_template

console = Console()

@click.command(name="status")
@click.option("--template", help="Optional template to compare against environment.")
@click.pass_context
def status_cmd(ctx, template):
    """Check cloud environment status and optional template compliance."""
    vars_dict = load_vars()
    project_id = vars_dict.get('gcp_project_id')
    
    if not project_id:
        console.print("[red]Error: No project ID found in terraform.tfvars or apigee.tfvars. Run 'apim init' first.[/red]")
        ctx.exit(1)

    console.print(f"\n[bold underline]ENVIRONMENT STATUS: {project_id}[/bold underline]")
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
    domain = vars_dict.get('domain_name')
    if domain:
        ssl = provider.get_ssl_certificate_status(project_id, domain)
        status = ssl.get("status", "UNKNOWN")
        actual_state["domain_name"] = domain
        actual_state["ssl_status"] = status
        console.print(f"  [green]✓ Domain Configed:[/green] {domain} [dim](SSL: {status})[/dim]")

    # 5. Template Compliance Check
    if template:
        try:
            tmpl_data = load_template(template)
            console.print(f"\n[bold underline]TEMPLATE COMPLIANCE: {Path(template).name}[/bold underline]")
            
            # Fields to check
            checks = [
                ("region", vars_dict.get("region")),
                ("domain_name", vars_dict.get("domain_name")),
                ("apigee_billing_type", vars_dict.get("apigee_billing_type", "EVALUATION")), # Fallback to eval for check
            ]
            
            for key, expected in tmpl_data.items():
                if expected is None: continue
                
                # Check against local config first, as it's the intent
                actual = vars_dict.get(key)
                
                # Special cases for defaults
                if key == "region" and not actual: actual = "us-central1"
                
                if actual == expected:
                    console.print(f"  [green]✓ {key}:[/green] {actual} (Match)")
                else:
                    console.print(f"  [red]✗ {key}:[/red] {actual or '[missing]'} (Expected: {expected})")
                    
        except Exception as e:
            console.print(f"[red]Error performing compliance check:[/red] {e}")

    console.print("")
