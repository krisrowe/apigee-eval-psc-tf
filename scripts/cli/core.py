import json
from pathlib import Path
import sys
import subprocess

# XDG Paths
XDG_CONFIG_HOME = Path.home() / ".config" / "apigee-tf"
CONFIG_ROOT = XDG_CONFIG_HOME / "projects"
STATE_ROOT = Path.home() / ".local" / "share" / "apigee-tf" / "states"
SETTINGS_FILE = XDG_CONFIG_HOME / "settings.json"

def api_get(path):
    """Helper to call Apigee API via curl + gcloud auth."""
    url = f"https://apigee.googleapis.com/v1/{path}"
    try:
        # Using shell invocation for $(...) access token expansion
        cmd = f"curl -s -H \"Authorization: Bearer $(gcloud auth print-access-token)\" {url}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                if "error" in data:
                    return None
                return data
            except json.JSONDecodeError:
                return None
    except Exception:
        return None
    return None

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
        except Exception as e:
            print(f"Warning: Failed to load {state_file}: {e}")
    return None
