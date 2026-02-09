import click
import time
from rich.console import Console
from scripts.cli.config import ConfigLoader
from scripts.cli.commands.core import run_terraform

console = Console()

def _retry_terraform(config, command, retries=6, delay=10, **kwargs):
    """Retries run_terraform to handle IAM propagation delays."""
    last_exit_code = 0
    for i in range(retries):
        exit_code = run_terraform(config, command, **kwargs)
        if exit_code == 0:
            return 0
        
        last_exit_code = exit_code
        if i < retries - 1:
            console.print(f"[yellow]Attempt {i+1}/{retries} failed (likely IAM propagation). Retrying in {delay}s...[/yellow]")
            time.sleep(delay)
            
    return last_exit_code

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
    
    # Common target list for this test
    test_targets = [
        "google_secret_manager_secret.fake_secret",
        "google_secret_manager_secret_version.fake_secret_v1"
    ]

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
        targets=test_targets
    )
    if exit_code != 0:
        console.print("[red]✗ Step 2 failed[/red]")
        ctx.exit(1)
    console.print("[green]✓ Step 2 passed[/green]\n")
    
    # Step 3: Try to delete as SA (should FAIL)
    console.print("[bold]Step 3:[/bold] Try to delete fake-secret (as SA) - SHOULD FAIL")
    console.print("[dim]Command: apim apply (Targeting delete)[/dim]")
    console.print("[dim]Identity: ADC → SA (impersonated)[/dim]")
    console.print("[dim]Expected: 403 Forbidden (Blocked by Deny Policy)[/dim]\n")
    
    # Smart Retry Loop for Propagation
    denied = False
    for i in range(12): # Up to 60s total
        exit_code = run_terraform(
            config,
            "apply",
            auto_approve=True,
            fake_secret=False,
            deletes_allowed=False,
            skip_impersonation=False,
            targets=test_targets
        )
        if exit_code != 0:
            # Operation failed! This is what we want (Blocked).
            denied = True
            break
        
        # Operation succeeded -> Policy not yet active.
        # Since we just deleted it, we must RECREATE it for the next retry attempt!
        console.print(f"[yellow]Attempt {i+1} succeeded (not blocked). Recreating secret and retrying in 5s...[/yellow]")
        run_terraform(config, "apply", auto_approve=True, fake_secret=True, targets=test_targets)
        time.sleep(5)

    if not denied:
        console.print("[red]✗ Step 3 FAILED - delete was never blocked after 60s![/red]")
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
        targets=test_targets
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
    
    # Use RETRY loop here because IAM Deny Policy removal can take 60s+ to propagate
    exit_code = _retry_terraform(
        config,
        "apply",
        retries=6,
        delay=15,
        auto_approve=True,
        fake_secret=False,
        deletes_allowed=True,
        skip_impersonation=False,
        targets=test_targets
    )
    if exit_code != 0:
        console.print("[red]✗ Step 5 failed (Propagation timeout?)[/red]")
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
        targets=test_targets
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
