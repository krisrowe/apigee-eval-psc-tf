import os
from pathlib import Path

def get_data_dir() -> Path:
    """
    Returns the global data directory for apigee-tf state (Persistent).
    Default: ~/.local/share/apigee-tf
    Override: APIGEE_TF_DATA_DIR env var
    """
    data_home = os.environ.get("APIGEE_TF_DATA_DIR")
    if data_home:
        return Path(data_home)
    return Path.home() / ".local/share/apigee-tf"

def get_cache_dir() -> Path:
    """
    Returns the cache directory for ephemeral staging.
    Default: ~/.cache/apigee-tf
    Override: XDG_CACHE_HOME
    """
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "apigee-tf"
    return Path.home() / ".cache" / "apigee-tf"

def get_state_path(project_id: str, phase: str = "1-main", suffix: str = None) -> Path:
    """
    Returns the path to the terraform state file for a specific project phase.
    Path: <DATA_DIR>/<project_id>[/<suffix>]/tf/<phase>/terraform.tfstate
    """
    root = get_data_dir() / project_id
    if suffix:
        root = root / suffix
    return root / "tf" / phase / "terraform.tfstate"
