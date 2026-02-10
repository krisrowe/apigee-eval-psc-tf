import json
from .schemas import ApigeeProjectStatus, ApigeeOrgConfig

def map_state_to_status(state_dict: dict) -> ApigeeProjectStatus:
    """
    Maps terraform show -json output to ApigeeProjectStatus.
    """
    if not state_dict:
        # Return empty status if state is missing
        return ApigeeProjectStatus(project_id="UNKNOWN", config=ApigeeOrgConfig(runtime_location="-"))

    resources = state_dict.get("resources", [])
    
    # Helper for safe access
    def get_first_inst_attr(resource_type):
        res = next((r for r in resources if r.get("type") == resource_type), {})
        instances = res.get("instances", [])
        if not instances: return {}
        return instances[0].get("attributes", {})

    # 1. Find Org
    org_attrs = get_first_inst_attr("google_apigee_organization")
    
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
    ssl_attrs = get_first_inst_attr("google_compute_managed_ssl_certificate")
    managed_list = ssl_attrs.get("managed", [])
    ssl_status = managed_list[0].get("status", "-") if managed_list else "-"

    # 5. Build Config (Immutable fields)
    tf_consumer_loc = org_attrs.get("api_consumer_data_location")
    tf_analytics_loc = org_attrs.get("analytics_region")
    
    # DRZ Detection
    is_drz = bool(tf_consumer_loc)
    
    # Infer Control Plane Location (Jurisdiction)
    control_plane_location = None
    
    if is_drz and tf_consumer_loc:
        if "northamerica" in tf_consumer_loc: control_plane_location = "ca"
        elif "europe" in tf_consumer_loc: control_plane_location = "eu"
        elif "australia" in tf_consumer_loc: control_plane_location = "au"
        elif "asia" in tf_consumer_loc: control_plane_location = "ap"
        elif "southamerica" in tf_consumer_loc: control_plane_location = "sa"
        elif "me-" in tf_consumer_loc: control_plane_location = "me"
        elif "in-" in tf_consumer_loc: control_plane_location = "in"
        else: control_plane_location = "us" # Fallback

    config = ApigeeOrgConfig(
        billing_type=org_attrs.get("billing_type", "-"),
        drz=is_drz,
        analytics_region=tf_analytics_loc,
        runtime_location=runtime_region,
        control_plane_location=control_plane_location,
        consumer_data_region=tf_consumer_loc
    )

    return ApigeeProjectStatus(
        project_id=org_attrs.get("project_id", "UNKNOWN"),
        config=config,
        subscription_type=org_attrs.get("subscription_type", "-"),
        environments=environments,
        instances=instances,
        ssl_status=ssl_status
    )
