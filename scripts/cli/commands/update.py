import click
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.commands.core import run_terraform
from scripts.cli.engine import TerraformStager
import subprocess
import shutil
import json
import subprocess
import shutil
import json

console = Console()

@click.command()
@click.option("--auto-approve", is_flag=True, help="Skip interactive approval.")
@click.pass_context
def update(ctx, auto_approve):
    """
    Day 2+ Maintenance: Updates existing Apigee installation.
    """
    try:
        root_dir = ConfigLoader.find_root()
        config = ConfigLoader.load(root_dir)
        
        # 1. State Pre-Check: Org MUST exist in Terraform State
        # We run 'terraform show -json' which reads local state WITHOUT refreshing/calling APIs.
        stager = TerraformStager(config)
        state_path = stager.staging_dir / "states" / "1-main" / "terraform.tfstate"
        
        org_found = False
        if state_path.exists():
            try:
                # We can run 'terraform show -json <state_path>' from anywhere
                tf_bin = shutil.which("terraform")
                
                cmd = [tf_bin, "show", "-json", str(state_path)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    state_json = json.loads(result.stdout)
                    # output -> values -> root_module -> resources[]
                    # or output -> values -> root_module -> child_modules[] -> resources[]
                    # 'terraform show -json' output structure involves recursive modules.
                    # Simplified scan for the resource type string in the raw text or simple json walk?
                    # Let's do a rigorous walk or just check the flattened 'values' if possible.
                    
                    # Robust recursive search for "google_apigee_organization"
                    def has_org(module):
                        for r in module.get("resources", []):
                            if r.get("type") == "google_apigee_organization":
                                return True
                        for child in module.get("child_modules", []):
                            if has_org(child):
                                return True
                        return False

                    if "values" in state_json and "root_module" in state_json["values"]:
                         if has_org(state_json["values"]["root_module"]):
                             org_found = True
            except Exception:
                pass 
        
        if not org_found:
            console.print(f"[red]Error: No Apigee Organization found in local state ({state_path}).[/red]")
            console.print("Use 'apim create' or 'apim import' to initialize.")
            ctx.exit(1)

        console.print(f"[bold blue]Updating Apigee ({config.project.gcp_project_id})...[/bold blue]")
        
        # 2. Run Terraform Apply
        exit_code = run_terraform(config, "apply", auto_approve=auto_approve)
        if exit_code != 0:
            console.print("[red]Update Failed.[/red]")
            ctx.exit(exit_code)
        console.print("[green]✓ Update Complete[/green]")
    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        ctx.exit(1)
