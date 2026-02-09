from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import CloudProvider
from ..schemas import ApigeeProjectStatus, ApigeeOrgConfig

class MockCloudProvider(CloudProvider):
    """
    In-memory mock for testing.
    """
    def __init__(self):
        self.orgs: Dict[str, Dict[str, Any]] = {}
        self.project_labels: Dict[str, Dict[str, str]] = {}
        self.instances: Dict[str, List[Dict[str, Any]]] = {}
        self.environments: Dict[str, List[str]] = {}
        self.ssl_certs: Dict[str, Dict[str, Any]] = {}
        self.deny_policies: Dict[str, Dict[str, Any]] = {}
        self.permissions: Dict[str, List[str]] = {} # principal -> [permissions]

    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        for pid, labels in self.project_labels.items():
            if labels.get(label_key) == label_value:
                return pid
        return None

    def get_status(self, project_id: str) -> Optional[ApigeeProjectStatus]:
        org_data = self.orgs.get(project_id)
        if not org_data:
            return None
            
        inst_list = self.instances.get(project_id, [])
        envs = self.environments.get(project_id, [])
        
        # Build Config component
        consumer_data_region = org_data.get("api_consumer_data_location")
        is_drz = bool(consumer_data_region)
        
        config = ApigeeOrgConfig(
            billing_type=org_data.get("billing_type", "EVALUATION"),
            drz=is_drz,
            runtime_location=inst_list[0].get("location") if inst_list else "-",
            analytics_region=org_data.get("analytics_region"),
            consumer_data_region=consumer_data_region,
            control_plane_location="ca" if is_drz else None
        )

        return ApigeeProjectStatus(
            project_id=project_id,
            config=config,
            subscription_type=org_data.get("subscription_type", "TRIAL"),
            environments=envs,
            instances=[i["name"] for i in inst_list],
            ssl_status="ACTIVE" if self.ssl_certs.get(project_id) else "-"
        )

    # Ad-hoc methods used by legacy test setup or direct mock manipulation
    def get_org(self, project_id): return self.orgs.get(project_id)
    def get_environments(self, project_id): return self.environments.get(project_id, [])

    # Ad-hoc methods used by Unit Tests (e.g. IAM Safety)
    def check_permission(self, project_id: str, principal: str, permission: str) -> bool:
        """
        Simulation logic: 
        1. Access is DENIED if any Deny Policy specifically blocks it for this principal.
        2. EXCEPTION: Unless the principal is listed as an exception in that policy.
        3. FALLBACK: Normal IAM Check (exists in self.permissions).
        """
        # 1. Deny Check
        for policy in self.deny_policies.values():
            for rule in policy.get("rules", []):
                deny = rule.get("deny_rule", {})
                if permission in deny.get("denied_permissions", []):
                    if principal in deny.get("denied_principals", []):
                        # 2. Exception Check
                        if principal in deny.get("exception_principals", []):
                            continue # Deny is bypassed
                        return False # EXPLICIT DENY WINS

        # 3. Allow Check
        allowed = self.permissions.get(principal, [])
        return "*" in allowed or permission in allowed
