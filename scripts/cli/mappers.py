import json
from .schemas import ApigeeProjectStatus, ApigeeOrgConfig

def map_state_to_status(state_dict: dict) -> ApigeeProjectStatus:
    """
    Maps terraform show -json output to ApigeeProjectStatus.
    """
    resources = state_dict.get("resources", [])
    
    # 1. Find Org
    org_res = next((r for r in resources if r.get("type") == "google_apigee_organization"), {})
    org_attrs = org_res.get("instances", [{}])[0].get("attributes", {})
    
    # 2. Find Instances
    inst_resources = [r for r in resources if r.get("type") == "google_apigee_instance"]
    runtime_region = "-"
    instances = []
    for r in inst_resources:
        for i in r.get("instances", []):
            attrs = i.get("attributes", {})
            name = attrs.get("name", "UNKNOWN")
            instances.append(name)
            if runtime_region == "-":
                runtime_region = attrs.get("location", "-")

    # 3. Find Environments
    env_resources = [r for r in resources if r.get("type") == "google_apigee_environment"]
    environments = []
    for r in env_resources:
        for i in r.get("instances", []):
            environments.append(i.get("attributes", {}).get("name"))

    # 4. Find SSL Status
    ssl_res = next((r for r in resources if r.get("type") == "google_compute_managed_ssl_certificate"), {})
    ssl_status = ssl_res.get("instances", [{}])[0].get("attributes", {}).get("managed", [{}])[0].get("status", "-")

    # 5. Build Config (Immutable fields)
    # control_plane_location is not in the resource attributes directly in standard provider, 
    # but we can infer it or rely on it being in the state's variables/outputs if needed.
    # For now, we use what's in the Org Resource.
    
    cp_loc = org_attrs.get("apigee_project_id", "").split("-")[0] # Rough heuristic if not explicit
    # Better: check for DRZ properties
    is_drz = org_attrs.get("disable_vpc_peering", False) # Often true for DRZ/PSC
    
    config = ApigeeOrgConfig(
        billing_type=org_attrs.get("billing_type", "-"),
        drz=is_drz,
        analytics_region=org_attrs.get("analytics_region"),
        runtime_location=runtime_region,
        control_plane_location=cp_loc if is_drz else None,
        consumer_data_region=org_attrs.get("api_consumer_data_location")
    )

    return ApigeeProjectStatus(
        project_id=org_attrs.get("project_id", "UNKNOWN"),
        config=config,
        subscription_type=org_attrs.get("subscription_type", "-"),
        environments=environments,
        instances=instances,
        ssl_status=ssl_status
    )
