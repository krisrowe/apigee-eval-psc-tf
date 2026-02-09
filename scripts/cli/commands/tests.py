import click
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.commands.core import run_terraform

console = Console()


def _run_deny_deletes_test(ctx):
    """
    Test deny policy enforcement for the terraform-deployer SA.
    
    Flow:
    1. Bootstrap (auto if SA missing)
    2. Create fake-secret as SA
    3. Try to delete as SA (should FAIL - deny policy blocks it)
    4. Remove deny policy as ADC (only USER can manage deny policies)
    5. Delete fake-secret as SA (should succeed - policy removed)
    6. Restore deny policy as ADC (only USER can manage deny policies)
    """
    root_dir = ConfigLoader.find_root()
    config = ConfigLoader.load(root_dir)
    
    console.print("\n[bold cyan]═══════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  DENY-DELETES TEST[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]\n")
    
    # Step 1: Bootstrap (automatic)
    console.print("[bold]Step 1:[/bold] Bootstrap (if needed)")
    console.print("[dim]Checking if SA exists in state...[/dim]\n")
    
    # Step 2: Create fake-secret as SA
    console.print("[bold]Step 2:[/bold] Create fake-secret (as SA)")
    console.print("[dim]Command: apim apply --fake-secret[/dim]")
    console.print("[dim]Identity: ADC → SA (impersonated)[/dim]")
    console.print("[dim]Deny policy: ON[/dim]\n")
    
    exit_code = run_terraform(
        config,
        "apply",
        auto_approve=True,
        fake_secret=True,
        deletes_allowed=False,
        skip_impersonation=False,
        targets=[
            "google_secret_manager_secret.fake_secret",
            "google_secret_manager_secret_version.fake_secret_v1"
        ]
    )
    if exit_code != 0:
        console.print("[red]✗ Step 2 failed[/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 2 passed[/green]\n")
    
    # Step 3: Try to delete as SA (should FAIL)
    console.print("[bold]Step 3:[/bold] Try to delete fake-secret (as SA) - SHOULD FAIL")
    console.print("[dim]Command: apim apply[/dim]")
    console.print("[dim]Identity: ADC → SA (impersonated)[/dim]")
    console.print("[dim]Expected: 403 Forbidden (deny policy blocks secretmanager.secrets.delete)[/dim]\n")
    
    exit_code = run_terraform(
        config,
        "apply",
        auto_approve=True,
        fake_secret=False,
        deletes_allowed=False,
        skip_impersonation=False,
        targets=[
            "google_secret_manager_secret.fake_secret",
            "google_secret_manager_secret_version.fake_secret_v1"
        ]
    )
    if exit_code == 0:
        console.print("[red]✗ Step 3 FAILED - delete should have been blocked![/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 3 passed (delete was blocked as expected)[/green]\n")
    
    # Step 4: Remove deny policy as ADC (only USER can manage deny policies)
    console.print("[bold]Step 4:[/bold] Remove deny policy (as ADC - only YOU can manage deny policies)")
    console.print("[dim]Command: apim apply --skip-impersonation --fake-secret --deletes-allowed[/dim]")
    console.print("[dim]Identity: ADC (direct, no impersonation)[/dim]")
    console.print("[dim]Action: Remove deny policy, keep fake-secret[/dim]\n")
    
    exit_code = run_terraform(
        config,
        "apply",
        auto_approve=True,
        fake_secret=True,
        deletes_allowed=True,
        skip_impersonation=True,
        targets=[
            "google_secret_manager_secret.fake_secret",
            "google_secret_manager_secret_version.fake_secret_v1"
        ]
    )
    if exit_code != 0:
        console.print("[red]✗ Step 4 failed[/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 4 passed[/green]\n")
    
    # Step 5: Delete fake-secret as SA (should succeed now)
    console.print("[bold]Step 5:[/bold] Delete fake-secret (as SA - policy removed)")
    console.print("[dim]Command: apim apply --deletes-allowed[/dim]")
    console.print("[dim]Identity: ADC → SA (impersonated)[/dim]")
    console.print("[dim]Expected: Success (deny policy removed in step 4)[/dim]\n")
    
    exit_code = run_terraform(
        config,
        "apply",
        auto_approve=True,
        fake_secret=False,
        deletes_allowed=True,
        skip_impersonation=False,
        targets=[
            "google_secret_manager_secret.fake_secret",
            "google_secret_manager_secret_version.fake_secret_v1"
        ]
    )
    if exit_code != 0:
        console.print("[red]✗ Step 5 failed[/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 5 passed[/green]\n")
    
    # Step 6: Restore deny policy as ADC (only USER can manage deny policies)
    console.print("[bold]Step 6:[/bold] Restore deny policy (as ADC - only YOU can manage deny policies)")
    console.print("[dim]Command: apim apply --skip-impersonation[/dim]")
    console.print("[dim]Identity: ADC (direct, no impersonation)[/dim]")
    console.print("[dim]Action: Recreate deny policy[/dim]\n")
    
    exit_code = run_terraform(
        config,
        "apply",
        auto_approve=True,
        fake_secret=False,
        deletes_allowed=False,
        skip_impersonation=True,
        targets=[
            "google_secret_manager_secret.fake_secret",
            "google_secret_manager_secret_version.fake_secret_v1"
        ]
    )
    if exit_code != 0:
        console.print("[red]✗ Step 6 failed[/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 6 passed[/green]\n")
    
    # Success
    console.print("[bold green]═══════════════════════════════════════════════════[/bold green]")
    console.print("[bold green]  ✓ ALL TESTS PASSED[/bold green]")
    console.print("[bold green]═══════════════════════════════════════════════════[/bold green]\n")


@click.group()
def tests():
    """Run test scenarios."""
    pass


@tests.command(name="run")
@click.argument("test_name")
@click.pass_context
def run_test(ctx, test_name):
    """Run a specific test."""
    if test_name == "deny-deletes":
        _run_deny_deletes_test(ctx)
    else:
        console.print(f"[red]Unknown test: {test_name}[/red]")
        console.print("[yellow]Available tests: deny-deletes[/yellow]")
        ctx.exit(1)
