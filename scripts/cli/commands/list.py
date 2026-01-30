from scripts.cli.core import CONFIG_ROOT, ensure_dirs

def cmd_list(args):
    """List all available project configurations."""
    ensure_dirs()
    projects = [p.stem for p in CONFIG_ROOT.glob("*.tfvars")]
        
    if not projects:
        print("No projects found in " + str(CONFIG_ROOT))
        return

    print("Available Projects (Local Configs):")
    for project in sorted(projects):
        print(f"  - {project}")
