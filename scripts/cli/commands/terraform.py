import sys
import subprocess
from scripts.cli.core import get_project_paths, ensure_dirs
from scripts.cli.config_sdk import get_config_manager

def run_terraform(action, name, extra_args):
    """Invoke terraform with project-specific state and vars."""
    var_file, state_file = get_project_paths(name)
    
    if not var_file.exists() and action != "init":
        print(f"Error: No project config found for '{name}'")
        sys.exit(1)
        
    ensure_dirs()
    
    # Load global settings
    config = get_config_manager().load()
    
    tf_cmd = ["terraform", action]

    if action != "init":
        tf_cmd.extend([
            f"-var-file={var_file}",
            f"-state={state_file}",
            f"-var=project_nickname={name}"
        ])
        
        # Pass global settings as variables if set
        if config.default_root_domain:
            tf_cmd.append(f"-var=default_root_domain={config.default_root_domain}")
    
    tf_cmd.extend(extra_args)
    print(f"Executing: {' '.join(tf_cmd)}")
    try:
        subprocess.run(tf_cmd, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
