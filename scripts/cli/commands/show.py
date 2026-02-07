import sys
import json
from pathlib import Path
from scripts.cli.core import get_project_paths, load_tfstate, load_vars, api_get, check_dns, check_ssl

# ANSI Colors
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

def cmd_show(args):
    """Show configuration and resource status for a project."""
    name = args.name
    var_file, state_file = get_project_paths(name)
    vars_dict = load_vars(name)
    project_id = vars_dict.get('gcp_project_id')
    
    def friendly_path(p):
        try:
            return str(p).replace(str(Path.home()), "~")
        except: return str(p)
    
    if args.raw:
        if var_file.exists():
            with open(var_file, 'r') as f:
                print(f.read(), end='')
        else:
            print(f"Error: Var file {var_file} not found.", file=sys.stderr)
            sys.exit(1)
        return

    print(f"\n{BOLD}PROJECT PROFILE: {CYAN}{name}{RESET}")
    print(f"  + Config: {friendly_path(var_file) if var_file.exists() else RED + 'MISSING' + RESET}")
    print(f"  + State:  {friendly_path(state_file) if state_file.exists() else YELLOW + 'NOT INITIALIZED' + RESET}")
    
    # 1. LIVE CLOUD STATUS (API PROBE)
    if project_id:
        print(f"\n{BOLD}CLOUD STATUS (Live API):{RESET}")
        org = api_get(f"organizations/{project_id}", name)
        if not org:
            print(f"    {RED}✗ Apigee Organization not found in {project_id}{RESET}")
        else:
            print(f"    {GREEN}✓ Apigee Organization:{RESET} {org.get('state')} ({org.get('billingType')})")
            
            # Probe Instances
            inst_data = api_get(f"organizations/{project_id}/instances", name)
            if inst_data and "instances" in inst_data:
                for inst in inst_data["instances"]:
                    print(f"    {GREEN}✓ Instance Found:{RESET}     {inst['name']} in {BOLD}{inst['location']}{RESET}")
            else:
                 print(f"    {YELLOW}⚠ No Instances found.{RESET}")

    # 2. LOCAL CONFIGURATION
    if var_file.exists():
        print(f"\n{BOLD}LOCAL CONFIGURATION (.tfvars):{RESET}")
        with open(var_file, 'r') as f:
            for line in f:
                if line.strip() and not line.strip().startswith("#"):
                    print(f"    {line.strip()}")
    
    # 3. RESOURCE TABLE (STATE)
    print(f"\n{BOLD}TRACKED RESOURCES (Terraform State):{RESET}")
    state = load_tfstate(name)
    
    if not state:
        print(f"    {YELLOW}Project not yet applied.{RESET}")
        print(f"\n{BOLD}NEXT STEPS:{RESET}")
        print(f"  Using Utility:")
        print(f"    {CYAN}./util plan {name}{RESET}")
        print(f"    {CYAN}./util apply {name}{RESET}")
        print(f"\n  Direct Terraform:")
        print(f"    terraform workspace select {name}")
        print(f"    terraform plan -var-file={var_file}")
        print(f"    terraform apply -var-file={var_file}")
    else:
        resources = state.get("resources", [])
        if not resources:
            print(f"    {YELLOW}State exists but contains no resources.{RESET}")
        else:
            print(f"    +--------------------------------+-----------+------------------------------------+")
            print(f"    | {BOLD}Resource                       {RESET}| {BOLD}Status    {RESET}| {BOLD}Resource ID / Details              {RESET}|")
            print(f"    +--------------------------------+-----------+------------------------------------+")
            
            for res in resources:
                rtype = res.get("type", "")
                base_name = res.get("name", "")
                for inst in res.get("instances", []):
                    friendly_name = f"{rtype}.{base_name}"
                    index = inst.get("index_key")
                    attrs = inst.get("attributes", {})
                    res_id = attrs.get("id", attrs.get("name", "N/A"))
                    
                    if rtype == "google_apigee_organization": friendly_name = "Apigee Organization"
                    elif rtype == "google_apigee_instance": friendly_name = f"Apigee Instance ({attrs.get('location', '?')})"
                    elif rtype == "google_apigee_environment": friendly_name = f"Environment: {index}"
                    elif rtype == "google_apigee_envgroup": friendly_name = f"EnvGroup: {index}"
                    elif rtype == "google_compute_global_address": friendly_name = "External IP (Ingress)"
                    
                    disp_name = (friendly_name[:30]).ljust(30)
                    status_str = f"{GREEN}✓ found{RESET}".ljust(18)
                    disp_id = (res_id[:34] if res_id else "N/A").ljust(34)
                    print(f"    | {disp_name} | {status_str} | {disp_id} |")
            
            print(f"    +--------------------------------+-----------+------------------------------------+")

    # 4. INGRESS & READINESS (Diagnostics)
    print(f"\n{BOLD}INGRESS & READINESS:{RESET}")
    # Get hostname from state
    from scripts.cli.commands.apis import get_environment_hostname
    try:
        hostname = get_environment_hostname(name, "dev")
        print(f"  + Hostname: {CYAN}{hostname}{RESET}")
        
        # DNS
        dns_ok, dns_ip = check_dns(hostname)
        dns_str = f"{GREEN}✓ Resolves to {dns_ip}{RESET}" if dns_ok else f"{YELLOW}⚠ NXDOMAIN (Pending Propagation){RESET}"
        print(f"  + DNS:      {dns_str}")
        
        # SSL
        if project_id:
            ssl_status, domain_status = check_ssl(project_id, hostname)
            if ssl_status == "ACTIVE":
                ssl_str = f"{GREEN}✓ ACTIVE{RESET}"
            elif ssl_status == "PROVISIONING":
                ssl_str = f"{YELLOW}⚠ PROVISIONING ({domain_status}){RESET}"
            else:
                ssl_str = f"{RED}✗ {ssl_status} ({domain_status}){RESET}"
            print(f"  + SSL Cert: {ssl_str}")
            
    except Exception:
        print(f"  {YELLOW}⚠ Ingress not yet configured or state missing.{RESET}")

    print(f"\n{BOLD}GCP LABELS:{RESET}")
    print(f"  apigee-tf: {CYAN}{name}{RESET}")
    
    # Contextual Guidance
    if not var_file.exists():
        print(f"\n{BOLD}NEXT ACTION:{RESET} ./util import {name} --project <id>")
    elif not state_file.exists():
        print(f"\n{BOLD}NEXT ACTION:{RESET} ./util plan {name}")
