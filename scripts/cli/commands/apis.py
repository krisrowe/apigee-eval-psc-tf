"""API Proxy management commands for the new CLI."""
import sys
import subprocess
import json
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

import click
from rich.console import Console

from scripts.cli.config import ConfigLoader

console = Console()


def find_proxy_bundle(proxy_name: str, project_root: Optional[Path] = None) -> Path:
    """
    Find a proxy bundle by name.
    
    Search order:
    1. $cwd/apiproxies/<proxy_name>/
    2. <install_dir>/apiproxies/<proxy_name>/
    
    Returns the path to the bundle directory.
    Raises FileNotFoundError if not found.
    """
    # 1. Check project root ($cwd or config root)
    if project_root is None:
        project_root = Path.cwd()
    
    cwd_path = project_root / "apiproxies" / proxy_name
    if cwd_path.exists() and (cwd_path / "apiproxy").exists():
        return cwd_path
    
    # 2. Check install directory (where this package is installed)
    # scripts/cli/commands/apis.py -> ../../.. = package root
    install_dir = Path(__file__).parents[3]
    install_path = install_dir / "apiproxies" / proxy_name
    if install_path.exists() and (install_path / "apiproxy").exists():
        return install_path
    
    # Not found
    searched = [str(cwd_path), str(install_path)]
    raise FileNotFoundError(
        f"Proxy bundle '{proxy_name}' not found.\n"
        f"Searched:\n  - {searched[0]}\n  - {searched[1]}"
    )


def get_proxy_base_path(bundle_path: Path, proxy_name: str) -> str:
    """Extract base path from proxy XML configuration."""
    proxy_xml = bundle_path / "apiproxy" / f"{proxy_name}.xml"
    
    if not proxy_xml.exists():
        # Try finding any .xml in apiproxy dir
        xml_files = list((bundle_path / "apiproxy").glob("*.xml"))
        if xml_files:
            proxy_xml = xml_files[0]
        else:
            return "/"
    
    tree = ET.parse(proxy_xml)
    root = tree.getroot()
    
    # Look for basepaths in ProxyEndpoint
    for proxy_endpoint in (bundle_path / "apiproxy" / "proxies").glob("*.xml"):
        ep_tree = ET.parse(proxy_endpoint)
        ep_root = ep_tree.getroot()
        
        http_proxy = ep_root.find(".//HTTPProxyConnection")
        if http_proxy is not None:
            base_path_elem = http_proxy.find("BasePath")
            if base_path_elem is not None and base_path_elem.text:
                return base_path_elem.text
    
    return "/"


def get_hostname_from_config(config) -> str:
    """Get the hostname from the config's domain setting."""
    return config.network.domain


@click.group()
def apis():
    """Manage API proxies (deploy, test)."""
    pass


@apis.command("deploy")
@click.argument("proxy_name")
@click.option("--env", "-e", default="dev", help="Target environment (default: dev)")
def deploy_command(proxy_name: str, env: str):
    """Deploy an API proxy to an environment."""
    try:
        config = ConfigLoader.load(Path.cwd())
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    
    # Find the proxy bundle
    try:
        bundle_path = find_proxy_bundle(proxy_name, config.root_dir)
        console.print(f"[dim]Found proxy at: {bundle_path}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    
    # Import (creates new revision)
    console.print(f"[bold]Importing proxy '{proxy_name}'...[/bold]")
    revision = import_proxy(config, proxy_name, bundle_path)
    
    if revision is None:
        console.print("[red]Import failed.[/red]")
        sys.exit(1)
    
    console.print(f"[green]✓ Imported revision {revision}[/green]")
    
    # Deploy
    console.print(f"[bold]Deploying to '{env}'...[/bold]")
    success = deploy_proxy(config, proxy_name, revision, env)
    
    if success:
        hostname = get_hostname_from_config(config)
        base_path = get_proxy_base_path(bundle_path, proxy_name)
        console.print(f"[green]✓ Deployed successfully![/green]")
        console.print(f"[dim]Endpoint: https://{hostname}{base_path}[/dim]")
    else:
        console.print("[red]Deployment failed.[/red]")
        sys.exit(1)


@apis.command("test")
@click.argument("proxy_name")
@click.option("--env", "-e", default="dev", help="Target environment (default: dev)")
def test_command(proxy_name: str, env: str):
    """Run integration tests for an API proxy."""
    try:
        config = ConfigLoader.load(Path.cwd())
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    
    # Find the proxy bundle
    try:
        bundle_path = find_proxy_bundle(proxy_name, config.root_dir)
        console.print(f"[dim]Found proxy at: {bundle_path}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    
    # Check for tests directory
    tests_dir = bundle_path / "tests"
    if not tests_dir.exists():
        console.print(f"[yellow]No tests directory found at {tests_dir}[/yellow]")
        sys.exit(0)
    
    test_files = sorted(tests_dir.glob("*.json"))
    if not test_files:
        console.print(f"[yellow]No test files (*.json) found in {tests_dir}[/yellow]")
        sys.exit(0)
    
    # Get endpoint info
    hostname = get_hostname_from_config(config)
    base_path = get_proxy_base_path(bundle_path, proxy_name)
    
    console.print(f"[bold]Testing: https://{hostname}{base_path}[/bold]")
    console.print()
    
    # Run tests
    passed = 0
    failed = 0
    
    for test_path in test_files:
        result = run_test(test_path, hostname, base_path)
        if result:
            passed += 1
        else:
            failed += 1
    
    console.print()
    if failed == 0:
        console.print(f"[green]✓ All {passed} test(s) passed![/green]")
    else:
        console.print(f"[red]✗ {failed} failed, {passed} passed[/red]")
        sys.exit(1)


def import_proxy(config, proxy_name: str, bundle_path: Path) -> Optional[str]:
    """Import a proxy bundle, returning the new revision number."""
    project_id = config.project.gcp_project_id
    control_plane = config.apigee.control_plane_location
    
    # Create temp zip
    temp_dir = tempfile.mkdtemp(prefix="apim-import-")
    temp_zip = Path(temp_dir) / f"{proxy_name}.zip"
    
    try:
        # Zip the bundle from parent so apiproxy/ is at the root of the archive
        # make_archive(base_name, format, root_dir, base_dir)
        shutil.make_archive(
            str(temp_zip.with_suffix('')), 
            'zip', 
            root_dir=bundle_path,  # Start from here
            base_dir='apiproxy'    # Include this folder
        )
        
        # Build API endpoint
        if control_plane:
            api_base = f"https://{control_plane}-apigee.googleapis.com/v1"
        else:
            api_base = "https://apigee.googleapis.com/v1"
        
        url = f"{api_base}/organizations/{project_id}/apis?name={proxy_name}&action=import"
        
        # Use curl to upload
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST", url,
                "-H", "Authorization: Bearer $(gcloud auth print-access-token)",
                "-H", "Content-Type: application/octet-stream",
                "--data-binary", f"@{temp_zip}"
            ],
            capture_output=True, text=True, shell=False
        )
        
        # Actually, use gcloud to get token properly
        token_result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True
        )
        token = token_result.stdout.strip()
        
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST", url,
                "-H", f"Authorization: Bearer {token}",
                "-H", "Content-Type: application/octet-stream",
                "--data-binary", f"@{temp_zip}"
            ],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            console.print(f"[red]curl failed: {result.stderr}[/red]")
            return None
        
        try:
            data = json.loads(result.stdout)
            if "error" in data:
                console.print(f"[red]API error: {data['error'].get('message', data['error'])}[/red]")
                return None
            return data.get("revision")
        except json.JSONDecodeError:
            console.print(f"[red]Invalid response: {result.stdout}[/red]")
            return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def deploy_proxy(config, proxy_name: str, revision: str, environment: str) -> bool:
    """Deploy a proxy revision to an environment."""
    project_id = config.project.gcp_project_id
    control_plane = config.apigee.control_plane_location
    
    if control_plane:
        api_base = f"https://{control_plane}-apigee.googleapis.com/v1"
    else:
        api_base = "https://apigee.googleapis.com/v1"
    
    url = f"{api_base}/organizations/{project_id}/environments/{environment}/apis/{proxy_name}/revisions/{revision}/deployments"
    
    token_result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True
    )
    token = token_result.stdout.strip()
    
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", url, "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True
    )
    
    try:
        data = json.loads(result.stdout)
        if "error" in data:
            console.print(f"[red]Deploy error: {data['error'].get('message', data['error'])}[/red]")
            return False
        return True
    except json.JSONDecodeError:
        # Empty response is OK for deployment
        return result.returncode == 0


def run_test(test_path: Path, hostname: str, base_path: str) -> bool:
    """Run a single test case."""
    try:
        with open(test_path) as f:
            test_case = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[red]Error loading {test_path.name}: {e}[/red]")
        return False
    
    test_name = test_case.get("name", test_path.stem)
    request_spec = test_case.get("request", {})
    expect_spec = test_case.get("expect", {})
    
    method = request_spec.get("method", "GET")
    path = request_spec.get("path", "/")
    full_url = f"https://{hostname}{base_path}{path}"
    
    console.print(f"[bold]{test_name}[/bold]: {method} {path}")
    
    # Build curl command
    curl_cmd = ["curl", "-s", "-w", "\n%{http_code}", "-X", method, full_url]
    
    headers = request_spec.get("headers", {})
    for k, v in headers.items():
        curl_cmd += ["-H", f"{k}: {v}"]
    
    body = request_spec.get("body")
    if body:
        curl_cmd += ["-d", json.dumps(body), "-H", "Content-Type: application/json"]
    
    result = subprocess.run(curl_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        console.print(f"  [red]✗ curl failed: {result.stderr}[/red]")
        return False
    
    # Parse response - last line is status code
    lines = result.stdout.strip().split("\n")
    status_code = int(lines[-1]) if lines else 0
    response_body = "\n".join(lines[:-1])
    
    # Check expectations
    expected_status = expect_spec.get("status")
    if expected_status and status_code != expected_status:
        console.print(f"  [red]✗ Expected status {expected_status}, got {status_code}[/red]")
        return False
    
    # Check body contains
    expected_contains = expect_spec.get("body_contains")
    if expected_contains and expected_contains not in response_body:
        console.print(f"  [red]✗ Response missing: {expected_contains}[/red]")
        return False
    
    console.print(f"  [green]✓ Passed (HTTP {status_code})[/green]")
    return True
