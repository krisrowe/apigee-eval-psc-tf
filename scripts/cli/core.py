import urllib.request
import urllib.error
import urllib.parse
import json
import subprocess
import os
from pathlib import Path
import hcl2

# XDG Paths
XDG_CONFIG_HOME = Path.home() / ".config" / "apigee-tf"
STATE_ROOT = Path.home() / ".local" / "share" / "apigee-tf" / "states"
SETTINGS_FILE = XDG_CONFIG_HOME / "settings.json"

def api_request(method, path, body=None, headers=None):
    """
    Make requests to the Apigee API using urllib.
    Real implementation for ApigeeAPIProvider.
    """
    try:
        # Get token from gcloud
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    except Exception:
        return 0, {"error": "GCloud auth failed"}

    # Determine Base URL
    base_url = "https://apigee.googleapis.com/v1"
    vars_dict = load_vars()
    
    # Handle nested 'apigee' block from HCL parsing
    apigee_conf = vars_dict.get("apigee", {})
    if isinstance(apigee_conf, list) and len(apigee_conf) > 0:
        apigee_conf = apigee_conf[0]
        
    cp_loc = apigee_conf.get("control_plane_location")
    
    # Also check if it's at the top level (legacy/flat config)
    if not cp_loc:
        cp_loc = vars_dict.get("control_plane_location")

    if cp_loc and not path.startswith("http"):
        base_url = f"https://{cp_loc}-apigee.googleapis.com/v1"

    url = f"{base_url}/{path}" if not path.startswith("http") else path
    
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "apim-cli/0.1.0"
    }
    if headers: req_headers.update(headers)

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return response.status, json.loads(res_body)
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except:
            err_body = e.reason
        return e.code, err_body
    except Exception as e:
        return 500, {"error": str(e)}

def load_settings():
    """Load global settings from JSON."""
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        except Exception:
            pass
    return settings

def save_settings(settings):
    """Save global settings to JSON."""
    XDG_CONFIG_HOME.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def ensure_dirs():
    """Ensure that the state directory exists."""
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

def get_project_paths():
    """
    Resolve paths for the local project.
    Checks for 'terraform.tfvars' or 'apigee.tfvars' in CWD.
    
    We parse the file manually here to avoid the overhead of the full engine load
    just to determine the state file location.
    """
    var_file = Path.cwd() / "terraform.tfvars"
    for fname in ["terraform.tfvars", "apigee.tfvars"]:
        candidate = Path.cwd() / fname
        if candidate.exists():
            var_file = candidate
            break

    project_id = None
    state_suffix = None
    
    if var_file.exists():
        try:
            with open(var_file, 'r') as f:
                # Use a lightweight regex check for the project ID
                # This ensures we find the ID even in nested or complex HCL blocks
                # without requiring a full HCL2 parse every time the CLI starts.
                import re
                content = f.read()
                pid_match = re.search(r'gcp_project_id\s*=\s*["\']([^"\']+)["\']', content)
                if pid_match:
                    project_id = pid_match.group(1)
                
                s_match = re.search(r'state_suffix\s*=\s*["\']([^"\']+)["\']', content)
                if s_match:
                    state_suffix = s_match.group(1)
        except Exception:
            pass

    state_name = project_id if project_id else "local"
    if state_suffix:
        state_name = f"{state_name}-{state_suffix}"
        
    state_file = STATE_ROOT / f"{state_name}.tfstate"
    return var_file, state_file

def load_vars():
    """Load variables from the local apigee.tfvars file."""
    var_file, _ = get_project_paths()
    if not var_file.exists():
        return {}
        
    try:
        with open(var_file, 'r') as f:
            data = hcl2.load(f)
            # Flatten HCL2 output which usually returns lists for every key
            return {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in data.items()}
    except Exception:
        return {}

def load_tfstate():
    """Load terraform state for the local project (Phase 1-main)."""
    # Assuming XDG_DATA_HOME/apigee-tf/<project_id>/tf/1-main/terraform.tfstate
    
    # 1. Get Project ID
    vars_dict = load_vars()
    project_id = vars_dict.get("gcp_project_id")
    if not project_id:
        return None
        
    # 2. Resolve Path
    data_home = os.environ.get("APIGEE_TF_DATA_DIR")
    if data_home:
        root = Path(data_home)
    else:
        root = Path.home() / ".local/share/apigee-tf"
        
    # TODO: Support state_suffix if we expose it in load_vars/config
    state_file = root / project_id / "tf" / "1-main" / "terraform.tfstate"
    
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None
    return None

def check_dns(hostname):
    """Check if the hostname resolves via DNS."""
    try:
        ip = socket.gethostbyname(hostname)
        return True, ip
    except socket.gaierror:
        return False, None
