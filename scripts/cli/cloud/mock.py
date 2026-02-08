from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import CloudProvider

class MockCloudProvider(CloudProvider):
    """
    In-memory mock for testing.
    """
    def __init__(self):
        self.orgs: Dict[str, Dict[str, Any]] = {}
        self.project_labels: Dict[str, Dict[str, str]] = {}
        self.instances: Dict[str, List[Dict[str, Any]]] = {}
        self.envgroups: Dict[str, List[Dict[str, Any]]] = {}
        self.environments: Dict[str, List[str]] = {}
        self.ssl_certs: Dict[str, Dict[str, Any]] = {}
        self.dns_zones: Dict[str, List[str]] = {}
        self.deny_policies: Dict[str, Dict[str, Any]] = {}
        self.permissions: Dict[str, List[str]] = {} # principal -> [permissions]

    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        for pid, labels in self.project_labels.items():
            if labels.get(label_key) == label_value:
                return pid
        return None

    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        return self.orgs.get(org_id)

    def list_instances(self, org_id: str) -> List[Dict[str, Any]]:
        return self.instances.get(org_id, [])

    def list_envgroups(self, org_id: str) -> List[Dict[str, Any]]:
        return self.envgroups.get(org_id, [])

    def get_environments(self, org_id: str) -> List[str]:
        return self.environments.get(org_id, [])

    def get_ssl_certificate_status(self, project_id: str, hostname: str) -> Dict[str, Any]:
        return self.ssl_certs.get(f"{project_id}/{hostname}", {"status": "NOT_FOUND"})

    def get_dns_nameservers(self, project_id: str, zone_name: str = "apigee-dns") -> List[str]:
        return self.dns_zones.get(f"{project_id}/{zone_name}", [])

    def get_deny_policy(self, project_id: str, policy_name: str) -> Optional[Dict[str, Any]]:
        return self.deny_policies.get(f"{project_id}/{policy_name}")

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
