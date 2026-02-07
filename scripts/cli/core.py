import json
from pathlib import Path
import sys
import subprocess
import socket

# XDG Paths
XDG_CONFIG_HOME = Path.home() / ".config" / "apigee-tf"
CONFIG_ROOT = XDG_CONFIG_HOME / "projects"
STATE_ROOT = Path.home() / ".local" / "share" / "apigee-tf" / "states"
SETTINGS_FILE = XDG_CONFIG_HOME / "settings.json"

def api_request(method, path, project_name=None, headers=None, body=None, files=None):
    """Helper to call Apigee API via curl + gcloud auth."""
    base_url = "https://apigee.googleapis.com/v1"
    
    if project_name:
        vars_dict = load_vars(project_name)
        cp_loc = vars_dict.get("control_plane_location")
        if cp_loc:
            base_url = f"https://{cp_loc}-apigee.googleapis.com/v1"

    url = f"{base_url}/{path}"
    
    cmd = ["curl", "-s", "-i", "-X", method]
    cmd += ["-H", f"Authorization: Bearer {subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True).stdout.strip()}"]
    
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
            
    if body:
        if isinstance(body, (dict, list)):
            cmd += ["-d", json.dumps(body)]
            cmd += ["-H", "Content-Type: application/json"]
        else:
            cmd += ["-d", str(body)]

    if files:
        for key, (filename, content, content_type) in files.items():
            # For simplicity in this env, we write to a temp file if it's not already a file
            if hasattr(content, 'read'):
                temp_f = tempfile.NamedTemporaryFile(delete=False)
                temp_f.write(content.read())
                temp_f.close()
                cmd += ["-F", f"{key}=@{temp_f.name};type={content_type}"]
            else:
                cmd += ["-F", f"{key}=@{content};type={content_type}"]

    cmd.append(url)
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            delimiter = '\r\n\r\n' if '\r\n\r\n' in res.stdout else '\n\n'
            parts = res.stdout.split(delimiter, 1)
            headers_part = parts[0]
            body_part = parts[1] if len(parts) > 1 else ""
            
            # Extract status code
            status_line = headers_part.splitlines()[0]
            status_code = int(status_line.split()[1])
            
            return status_code, body_part
    except Exception as e:
        print(f"Error executing curl: {e}", file=sys.stderr)
    return 500, ""

def load_settings():
    """Load global settings from JSON."""
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        except Exception as e:
            print(f"Error: Failed to load {SETTINGS_FILE}: {e}")
            sys.exit(1)
    return settings

def save_settings(settings):
    """Save global settings to JSON."""
    XDG_CONFIG_HOME.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def ensure_dirs():
    """Ensure that the config and state directories exist."""
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

def get_project_paths(name):
    """Resolve paths for a given project name."""
    var_file = CONFIG_ROOT / f"{name}.tfvars"
    state_file = STATE_ROOT / f"{name}.tfstate"
    return var_file, state_file

def load_vars(name):
    """Load variables from a project's .tfvars file."""
    var_file, _ = get_project_paths(name)
    vars_dict = {}
    if var_file.exists():
        with open(var_file, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.split('=', 1)
                    vars_dict[k.strip()] = v.strip().strip('"').strip("'")
    return vars_dict

def load_tfstate(name):
    """Load terraform state for a project."""
    _, state_file = get_project_paths(name)
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Empty or invalid state file -> treat as not applied
            return None
    return None

def check_dns(hostname):
    """Check if the hostname resolves via DNS."""
    try:
        ip = socket.gethostbyname(hostname)
        return True, ip
    except socket.gaierror:
        return False, None

def check_ssl(project_id, hostname):
    """Check the status of Google-managed SSL certificates."""
    try:
        # List all global SSL certificates and find the one matching our domain
        result = subprocess.run(
            ["gcloud", "compute", "ssl-certificates", "list", "--project", project_id, "--global", "--format=json"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return "UNKNOWN", f"Error querying gcloud: {result.stderr}"
        
        certs = json.loads(result.stdout)
        # Find certificates that include our hostname in their 'managed' domains
        relevant_certs = [
            c for c in certs 
            if c.get("managed", {}).get("domains") and hostname in c["managed"]["domains"]
        ]
        
        if not relevant_certs:
            return "NOT_FOUND", "No managed SSL certificate found for this domain."
            
        # Get the latest one
        cert = relevant_certs[0]
        status = cert.get("managed", {}).get("status", "UNKNOWN")
        domain_status = cert.get("managed", {}).get("domainStatus", {}).get(hostname, "UNKNOWN")
        
        return status, domain_status
    except Exception as e:
        return "ERROR", str(e)

def get_nameservers(project_id, zone_name="apigee-dns"):
    """Fetch assigned name servers for a GCP managed DNS zone."""
    try:
        result = subprocess.run(
            ["gcloud", "dns", "managed-zones", "describe", zone_name, "--project", project_id, "--format=json"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        return data.get("nameServers", [])
    except Exception:
        return None
