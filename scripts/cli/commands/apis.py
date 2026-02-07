import sys
import subprocess
import json
import tempfile
import shutil
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.cli.core import load_vars

def cmd_apis(args):
    """Command to manage/list APIs."""
    if args.action == "list":
        list_apis(args.name)
    elif args.action == "import":
        import_api(args.name, args.proxy_name, args.bundle, args.output_json)
    elif args.action == "deploy":
        deploy_api(args.name, args.proxy_name, args.revision, args.environment)
    elif args.action == "undeploy":
        undeploy_api(args.name, args.proxy_name, args.revision, args.environment)
    elif args.action == "test":
        test_api(args.name, args.proxy_name, args.bundle, args.environment, args.test_file)
    else:
        print(f"Unknown action: {args.action}")

def get_access_token():
    """Get GCP access token using gcloud."""
    result = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Failed to get access token: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def get_base_url(project_alias):
    """Get the Apigee API base URL for a project."""
    vars_dict = load_vars(project_alias)
    project_id = vars_dict.get("gcp_project_id")
    cp_loc = vars_dict.get("control_plane_location")
    
    if not project_id:
        print(f"ERROR: Could not find project ID for alias '{project_alias}'.", file=sys.stderr)
        sys.exit(1)
    
    base_url = f"https://{cp_loc}-apigee.googleapis.com/v1" if cp_loc else "https://apigee.googleapis.com/v1"
    return base_url, project_id

def list_apis(project_alias):
    """List API proxies for a project."""
    base_url, project_id = get_base_url(project_alias)
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Listing APIs for project '{project_id}' ({project_alias})...")
    
    response = requests.get(f"{base_url}/organizations/{project_id}/apis", headers=headers)
    
    if response.status_code != 200:
        print(f"ERROR: Failed to list APIs (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)
    
    data = response.json()
    proxies = data.get("proxies", [])
    
    if not proxies:
        print("  [+] No API proxies found.")
    else:
        print(f"  [+] Found {len(proxies)} API proxy(ies):")
        for proxy in proxies:
            print(f"      - {proxy.get('name')}")

def import_api(project_alias, proxy_name, bundle_path, output_json=False):
    """Import an API proxy bundle (creates a new revision)."""
    base_url, project_id = get_base_url(project_alias)
    
    # Handle bundle path - if it's a directory, zip it to a temp location
    bundle_file = Path(bundle_path)
    temp_zip = None
    
    if bundle_file.is_dir():
        if not output_json:
            print(f"Creating temporary zip from directory '{bundle_path}'...")
        temp_dir = tempfile.mkdtemp(prefix="apigee-import-")
        temp_zip = Path(temp_dir) / f"{proxy_name}.zip"
        
        # Create zip archive
        shutil.make_archive(str(temp_zip.with_suffix('')), 'zip', bundle_path)
        bundle_path = str(temp_zip)
        if not output_json:
            print(f"  [+] Created temporary bundle: {bundle_path}")
    elif not bundle_file.exists():
        print(f"ERROR: Bundle file/directory not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Get access token
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Import the bundle
        if not output_json:
            print(f"Importing proxy '{proxy_name}' from bundle '{bundle_path}'...")
        import_url = f"{base_url}/organizations/{project_id}/apis?name={proxy_name}&action=import"
        
        with open(bundle_path, 'rb') as f:
            files = {'file': (Path(bundle_path).name, f, 'application/zip')}
            response = requests.post(import_url, headers=headers, files=files)
        
        if response.status_code not in [200, 201]:
            print(f"ERROR: Failed to import proxy (HTTP {response.status_code}): {response.text}", file=sys.stderr)
            sys.exit(1)
        
        import_data = response.json()
        if "error" in import_data:
            print(f"ERROR: API returned error: {import_data['error']}", file=sys.stderr)
            sys.exit(1)
        
        revision = import_data.get("revision")
        
        if output_json:
            # Output JSON for scripting
            print(json.dumps({"revision": revision, "name": proxy_name}))
        else:
            print(f"  [+] Imported revision: {revision}")
        
        return revision
    
    finally:
        # Clean up temp directory if we created one
        if temp_zip and temp_zip.parent.exists():
            shutil.rmtree(temp_zip.parent)
            if not output_json:
                print(f"  [+] Cleaned up temporary files")

def deploy_api(project_alias, proxy_name, revision, environment):
    """Deploy a specific API proxy revision to an environment."""
    base_url, project_id = get_base_url(project_alias)
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Deploying proxy '{proxy_name}' revision {revision} to environment '{environment}'...")
    deploy_url = f"{base_url}/organizations/{project_id}/environments/{environment}/apis/{proxy_name}/revisions/{revision}/deployments"
    
    response = requests.post(deploy_url, headers=headers)
    
    if response.status_code not in [200, 201]:
        print(f"ERROR: Failed to deploy proxy (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)
    
    try:
        deploy_data = response.json()
        if "error" in deploy_data:
            print(f"ERROR: Deployment failed: {deploy_data['error']}", file=sys.stderr)
            sys.exit(1)
    except json.JSONDecodeError:
        pass  # Some deployments return empty body
    
    print(f"  [+] Successfully deployed '{proxy_name}' revision {revision} to '{environment}'")

def undeploy_api(project_alias, proxy_name, revision, environment):
    """Undeploy an API proxy revision from an environment."""
    base_url, project_id = get_base_url(project_alias)
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Undeploying proxy '{proxy_name}' revision {revision} from environment '{environment}'...")
    undeploy_url = f"{base_url}/organizations/{project_id}/environments/{environment}/apis/{proxy_name}/revisions/{revision}/deployments"
    
    response = requests.delete(undeploy_url, headers=headers)
    
    if response.status_code not in [200, 204]:
        print(f"ERROR: Failed to undeploy proxy (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)
    
    print(f"  [+] Successfully undeployed '{proxy_name}' revision {revision} from '{environment}'")

def get_proxy_base_path(bundle_path, proxy_name):
    """Extract base path from proxy XML configuration."""
    bundle_dir = Path(bundle_path)
    
    # Look for the proxy XML file to get ProxyEndpoint name
    proxy_xml = bundle_dir / 'apiproxy' / f'{proxy_name}.xml'
    
    if not proxy_xml.exists():
        print(f"ERROR: Proxy XML not found at {proxy_xml}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Parse root proxy XML to find ProxyEndpoint
        tree = ET.parse(proxy_xml)
        root = tree.getroot()
        
        proxy_endpoints = root.find('ProxyEndpoints')
        if proxy_endpoints is None:
            print(f"ERROR: No ProxyEndpoints found in {proxy_xml}", file=sys.stderr)
            sys.exit(1)
        
        # Get first ProxyEndpoint name (usually 'default')
        proxy_endpoint_elem = proxy_endpoints.find('ProxyEndpoint')
        if proxy_endpoint_elem is None or not proxy_endpoint_elem.text:
            print(f"ERROR: No ProxyEndpoint element found", file=sys.stderr)
            sys.exit(1)
        
        proxy_endpoint_name = proxy_endpoint_elem.text.strip()
        
        # Now parse the ProxyEndpoint XML file
        proxy_endpoint_xml = bundle_dir / 'apiproxy' / 'proxies' / f'{proxy_endpoint_name}.xml'
        
        if not proxy_endpoint_xml.exists():
            print(f"ERROR: ProxyEndpoint XML not found at {proxy_endpoint_xml}", file=sys.stderr)
            sys.exit(1)
        
        endpoint_tree = ET.parse(proxy_endpoint_xml)
        endpoint_root = endpoint_tree.getroot()
        
        # Find BasePath in HTTPProxyConnection
        http_proxy_conn = endpoint_root.find('HTTPProxyConnection')
        if http_proxy_conn is not None:
            base_path_elem = http_proxy_conn.find('BasePath')
            if base_path_elem is not None and base_path_elem.text:
                return base_path_elem.text.strip()
        
        print(f"ERROR: No BasePath found in {proxy_endpoint_xml}", file=sys.stderr)
        sys.exit(1)
    except ET.ParseError as e:
        print(f"ERROR: Failed to parse proxy XML: {e}", file=sys.stderr)
        sys.exit(1)

def get_environment_hostname(project_alias, environment):
    """Get the hostname for an Apigee environment by querying Terraform state."""
    # State file is in ~/.local/share/apigee-tf/states/
    state_dir = Path.home() / '.local' / 'share' / 'apigee-tf' / 'states'
    state_file = state_dir / f'{project_alias}.tfstate'
    
    if not state_file.exists():
        print(f"ERROR: Terraform state not found at {state_file}", file=sys.stderr)
        print(f"Run './util apply {project_alias}' first to create infrastructure.", file=sys.stderr)
        sys.exit(1)
    
    # Query terraform output for envgroup_hostname using JSON output
    try:
        result = subprocess.run(
            ['terraform', 'output', '-state', str(state_file), '-json'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            outputs = json.loads(result.stdout)
            
            # Try envgroup_hostname output first
            if 'envgroup_hostname' in outputs:
                return outputs['envgroup_hostname']['value']
        
        # Fallback: try domain_name from tfvars
        vars_dict = load_vars(project_alias)
        hostname = vars_dict.get('domain_name')
        
        if hostname:
            print(f"WARNING: Using domain_name from tfvars (envgroup_hostname output not found)", file=sys.stderr)
            return hostname
        
        print(f"ERROR: Could not determine hostname for '{project_alias}'", file=sys.stderr)
        print(f"Run 'terraform apply' to populate outputs or add domain_name to tfvars.", file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        print(f"ERROR: Failed to query terraform output: {e}", file=sys.stderr)
        sys.exit(1)

def test_api(project_alias, proxy_name, bundle_path, environment, test_file=None):
    """Run integration tests for an API proxy."""
    bundle_dir = Path(bundle_path)
    tests_dir = bundle_dir / 'tests'
    
    if not tests_dir.exists():
        print(f"ERROR: Tests directory not found at {tests_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Get base path from proxy XML
    base_path = get_proxy_base_path(bundle_path, proxy_name)
    print(f"Discovered base path: {base_path}")
    
    # Get environment hostname
    hostname = get_environment_hostname(project_alias, environment)
    
    # --- Pre-flight Diagnostics ---
    from scripts.cli.core import check_dns, check_ssl
    print(f"Pre-flight check for {hostname}...")
    
    dns_ok, _ = check_dns(hostname)
    vars_dict = load_vars(project_alias)
    project_id = vars_dict.get("gcp_project_id")
    
    ssl_status = "UNKNOWN"
    if project_id:
        ssl_status, _ = check_ssl(project_id, hostname)

    if not dns_ok or ssl_status != "ACTIVE":
        print("-" * 40)
        if not dns_ok:
            print("[ ] DNS Resolution: PENDING (NXDOMAIN)")
            print("    Advice: Wait 1-5 minutes for DNS propagation.")
        if ssl_status == "PROVISIONING":
            print("[ ] SSL Certificate: PROVISIONING")
            print("    Advice: Google-managed certificates take 15-60 minutes.")
        print("-" * 40)
        print("\nWARNING: Infrastructure is not fully ready. Tests will likely fail.")
        confirm = input("Do you want to continue anyway? (y/N): ")
        if confirm.lower() != 'y':
            sys.exit(0)
    else:
        print("[✓] Infrastructure is READY.")
    
    print(f"Testing against: https://{hostname}")
    print()
    
    # Find test files
    if test_file:
        test_files = [Path(test_file)]
    else:
        test_files = sorted(tests_dir.glob('*.json'))
    
    if not test_files:
        print(f"ERROR: No test files found in {tests_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Run tests
    passed = 0
    failed = 0
    
    for test_path in test_files:
        try:
            with open(test_path) as f:
                test_case = json.load(f)
            
            test_name = test_case.get('name', test_path.name)
            request_spec = test_case.get('request', {})
            expect_spec = test_case.get('expect', {})
            
            # Build full URL
            method = request_spec.get('method', 'GET')
            path = request_spec.get('path', '/')
            full_url = f"https://{hostname}{base_path}{path}"
            
            headers = request_spec.get('headers', {})
            body = request_spec.get('body')
            
            # Execute request
            print(f"Running: {test_name}")
            print(f"  {method} {full_url}")
            
            response = requests.request(
                method=method,
                url=full_url,
                headers=headers,
                json=body if body else None,
                verify=True
            )
            
            # Validate response
            test_passed = True
            
            # Check status code
            expected_status = expect_spec.get('status')
            if expected_status and response.status_code != expected_status:
                print(f"  ✗ FAIL: Expected status {expected_status}, got {response.status_code}")
                test_passed = False
            
            # Check headers
            expected_headers = expect_spec.get('headers', {})
            for header, value in expected_headers.items():
                actual_value = response.headers.get(header)
                if actual_value != value:
                    print(f"  ✗ FAIL: Expected header {header}={value}, got {actual_value}")
                    test_passed = False
            
            # Check body contains
            body_contains = expect_spec.get('body_contains', [])
            response_text = response.text
            for substring in body_contains:
                if substring not in response_text:
                    print(f"  ✗ FAIL: Expected body to contain '{substring}'")
                    test_passed = False
            
            if test_passed:
                print(f"  ✓ PASS")
                passed += 1
            else:
                failed += 1
            
            print()
        
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            print()
            failed += 1
    
    # Summary
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        sys.exit(1)
