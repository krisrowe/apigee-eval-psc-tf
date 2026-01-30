import json
import subprocess
import sys
from pathlib import Path
from scripts.cli.core import get_project_paths, ensure_dirs, load_vars, load_settings, api_get
from scripts.cli.template import load_template

def cmd_import(args):
    """
    Unified Import.
    
    Resolution Priority:
    1. Template (if provided) - Conflicts with Cloud/Existing = FAIL
    2. GCP Discovery (Truth)
    3. Existing Config (tfvars)
    """
    name = args.name
    force = getattr(args, 'force', False)
    
    var_file, state_file = get_project_paths(name)
    existing_vars = load_vars(name)
    settings = load_settings()

    # --- 1. Load Template ---
    template_data = {}
    if args.template:
        try:
            template_data = load_template(args.template)
            print(f"Loaded template: {args.template}")
        except Exception as e:
            print(f"ERROR: Failed to load template: {e}")
            sys.exit(1)

    # --- 2. Resolve Project ID ---
    print(f"Searching for project with label 'apigee-tf:{name}'...")
    discovered_project_id = None
    try:
        cmd = ["gcloud", "projects", "list", f"--filter=labels.apigee-tf:{name}", "--format=json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        projects = json.loads(result.stdout)
        if projects:
            discovered_project_id = projects[0]['projectId']
            print(f"  [+] Found Project ID via Label: {discovered_project_id}")
    except Exception as e:
        print(f"  [!] Warning: Project discovery failed: {e}")

    # Priority: Template -> Discovered -> Arg -> Existing
    requested_project_id = (
        template_data.get("gcp_project_id") or 
        discovered_project_id or 
        args.project or 
        existing_vars.get("gcp_project_id")
    )

    if not requested_project_id:
        print(f"ERROR: Could not determine Project ID. Use --project, provide a template, or label a project with 'apigee-tf:{name}'.")
        sys.exit(1)
        
    # Check for Project ID Conflict
    if discovered_project_id and requested_project_id != discovered_project_id:
        print(f"CRITICAL CONFLICT: Label says '{discovered_project_id}' but you requested '{requested_project_id}'.")
        sys.exit(1)

    print(f"Target Project ID: {requested_project_id}")

    # Check for Existing Config Conflict 
    existing_config_pid = existing_vars.get("gcp_project_id")
    if existing_config_pid and existing_config_pid != requested_project_id:
        if not force:
            print(f"CRITICAL: Name '{name}' is already attached to '{existing_config_pid}'.")
            print(f"Action: Use --force to clear state.")
            sys.exit(1)
        else:
            print(f"WARNING: --force detected. Clearing existing config/state for '{name}'...")
            if var_file.exists(): var_file.unlink()
            if state_file.exists(): state_file.unlink()
            existing_vars = {}

    # --- 3. Probe Cloud (Truth) ---
    print(f"Probing Apigee API...")
    
    disc_analytics = None
    disc_control_plane = None
    disc_runtime = None
    
    org_data = api_get(f"organizations/{requested_project_id}")
    
    imports = []
    discovered_env_names = []
    discovered_eg_names = []
    
    if org_data:
        print(f"  [+] Found Apigee Org (State: {org_data.get('state')})")
        disc_analytics = org_data.get("analyticsRegion")
        if disc_analytics:
            print(f"      Analytics Region: {disc_analytics}")
            
        api_consumer_data_loc = org_data.get("apiConsumerDataLocation")
        if api_consumer_data_loc:
            if api_consumer_data_loc.startswith("northamerica-northeast"):
                disc_control_plane = "ca"
            elif api_consumer_data_loc.startswith("europe-"):
                disc_control_plane = "eu"
            print(f"      Control Plane: {disc_control_plane or 'Global'} (from {api_consumer_data_loc})")
            
        imports.append({
            "to": "module.apigee_core.google_apigee_organization.apigee_org",
            "id": f"organizations/{requested_project_id}"
        })
        
        # Detect Runtime (Instance)
        instances_resp = api_get(f"organizations/{requested_project_id}/instances")
        if instances_resp and instances_resp.get("instances"):
            for inst in instances_resp["instances"]:
                 disc_runtime = inst.get("location")
                 print(f"  [+] Found Instance: {inst['name']} in {disc_runtime}")
                 imports.append({
                    "to": "module.apigee_core.google_apigee_instance.apigee_instance",
                    "id": f"organizations/{requested_project_id}/instances/{inst['name']}"
                 })
        
        # Detect Env Groups
        eg_resp = api_get(f"organizations/{requested_project_id}/envgroups")
        if eg_resp and eg_resp.get("environmentGroups"):
            for eg in eg_resp['environmentGroups']:
                discovered_eg_names.append(eg['name'])
                imports.append({
                    "to": f'module.apigee_core.google_apigee_envgroup.envgroup["{eg["name"]}"]',
                    "id": f'organizations/{requested_project_id}/envgroups/{eg["name"]}'
                })

        # Detect Environments
        envs_resp = api_get(f"organizations/{requested_project_id}/environments")
        if envs_resp and isinstance(envs_resp, list):
            discovered_env_names = envs_resp
            for env in discovered_env_names:
                 imports.append({
                     "to": f'module.apigee_core.google_apigee_environment.apigee_env["{env}"]',
                     "id": f'organizations/{requested_project_id}/environments/{env}'
                 })


    # --- 4. Resolve Settings ---
    final_vars = {}
    
    def resolve(key, template_val, discovered_val, existing_val, default_val=None):
        """Strict Priority: Template -> Discovery -> Existing -> Default"""
        
        # Conflict Check
        if template_val is not None and discovered_val is not None:
             t_norm = template_val or ""
             d_norm = discovered_val or ""
             if t_norm and d_norm and t_norm != d_norm:
                 print(f"\nCRITICAL CONFLICT on '{key}':")
                 print(f"  Template:  {template_val}")
                 print(f"  Discovery: {discovered_val} (Immutable Cloud Truth)")
                 print("Template disagrees with Cloud. Aborting.")
                 sys.exit(1)
        
        if template_val is not None: return template_val
        
        if discovered_val is not None:
            if existing_val and existing_val != discovered_val:
                print(f"  [!] Updating '{key}': {existing_val} -> {discovered_val} (Cloud Truth)")
            return discovered_val
            
        if existing_val is not None: return existing_val
        return default_val

    # Resolve Variables
    final_vars['project_nickname'] = resolve('project_nickname', template_data.get("project_nickname"), None, existing_vars.get("project_nickname"), default_val=name)

    domain_tmpl_val = None
    dt = settings.get("domain_template")
    if dt: domain_tmpl_val = dt.format(nickname=name)
        
    final_vars['domain_name'] = resolve('domain_name', 
                                        template_data.get("domain_name"), 
                                        None, 
                                        existing_vars.get("domain_name"), 
                                        domain_tmpl_val)

    final_vars['apigee_analytics_region'] = resolve('apigee_analytics_region',
                                                    template_data.get("apigee_analytics_region"),
                                                    disc_analytics,
                                                    existing_vars.get("apigee_analytics_region"))

    final_vars['apigee_runtime_location'] = resolve('apigee_runtime_location',
                                                    template_data.get("apigee_runtime_location"),
                                                    disc_runtime,
                                                    existing_vars.get("apigee_runtime_location"))
                                                    
    final_vars['control_plane_location'] = resolve('control_plane_location',
                                                   template_data.get("control_plane_location"),
                                                   disc_control_plane,
                                                   existing_vars.get("control_plane_location"),
                                                   default_val="")

    # --- 5. Validate Final Config ---
    missing = []
    if not final_vars['apigee_analytics_region']: missing.append("apigee_analytics_region")
    if not final_vars['apigee_runtime_location']: missing.append("apigee_runtime_location")
    if not final_vars['domain_name']: missing.append("domain_name")
    
    # Heuristic: runtime = analytics if missing
    if final_vars['apigee_analytics_region'] and not final_vars['apigee_runtime_location']:
        final_vars['apigee_runtime_location'] = final_vars['apigee_analytics_region']
        if "apigee_runtime_location" in missing: missing.remove("apigee_runtime_location")

    if missing:
        print(f"\nERROR: Missing required configuration: {', '.join(missing)}")
        print("Provide via --template or ensure resources exist in GCP.")
        sys.exit(1)

    # --- 6. Write Configuration ---
    ensure_dirs()
    
    try:
        with open(var_file, 'w') as f:
            f.write(f'gcp_project_id          = "{requested_project_id}"\n')
            f.write(f'domain_name             = "{final_vars["domain_name"]}"\n')
            f.write(f'apigee_analytics_region = "{final_vars["apigee_analytics_region"]}"\n')
            f.write(f'apigee_runtime_location = "{final_vars["apigee_runtime_location"]}"\n')
            f.write(f'project_nickname        = "{final_vars["project_nickname"]}"\n')
            
            val = final_vars["control_plane_location"]
            if val is not None:
                 f.write(f'control_plane_location  = "{val}"\n')
                 
            # Write mapped maps if new discovery
            if discovered_env_names:
                env_map = "{\n" + ",\n".join([f'    "{e}" = {{}}' for e in discovered_env_names]) + "\n  }"
                f.write(f'\nenvironments = {env_map}\n')
            
            if discovered_eg_names:
                eg_map = "{\n" + ",\n".join([f'    "{eg}" = {json.dumps(discovered_env_names)}' for eg in discovered_eg_names]) + "\n  }"
                f.write(f'envgroups = {eg_map}\n')
                 
        print(f"\nConfiguration saved to {var_file}")
        
    except Exception as e:
        print(f"ERROR: Failed to write config file: {e}")
        sys.exit(1)

    # --- 7. Generate Import Plan ---
    if imports:
        import_file = Path("generated_imports.tf")
        with open(import_file, 'w') as f:
            f.write("# Generated by ./util import\n\n")
            for imp in imports:
                f.write(f'import {{\n  to = {imp["to"]}\n  id = "{imp["id"]}"\n}}\n\n')
        print(f"\nGenerated {import_file} with {len(imports)} resources.")
    else:
        print("\nProject truly empty. Ready for 'apply'.")
