import json
from typing import Optional, List, Dict, Any
from .base import CloudProvider
from ..core import api_request

class ApigeeAPIProvider(CloudProvider):
    """
    Real-world Apigee API provider using urllib via core.api_request.
    """

    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        import subprocess
        try:
            result = subprocess.run(
                ["gcloud", "projects", "list", f"--filter=labels.{label_key}:{label_value}", "--format=value(projectId)", "--limit=1"],
                capture_output=True, text=True
            )
            return result.stdout.strip() or None
        except:
            return None

    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        status, data = api_request("GET", f"organizations/{org_id}")
        return data if status == 200 else None

    def list_instances(self, org_id: str) -> List[Dict[str, Any]]:
        status, data = api_request("GET", f"organizations/{org_id}/instances")
        if status == 200 and data:
            return data.get("instances", [])
        return []

    def list_envgroups(self, org_id: str) -> List[Dict[str, Any]]:
        status, data = api_request("GET", f"organizations/{org_id}/envgroups")
        if status == 200 and data:
            return data.get("environmentGroups", [])
        return []

    def get_environments(self, org_id: str) -> List[str]:
        status, data = api_request("GET", f"organizations/{org_id}/environments")
        return data if status == 200 else []

    def get_ssl_certificate_status(self, project_id: str, hostname: str) -> Dict[str, Any]:
        import subprocess
        try:
            result = subprocess.run(
                ["gcloud", "compute", "ssl-certificates", "list", "--project", project_id, "--global", "--format=json"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return {"status": "UNKNOWN", "error": result.stderr}
            
            certs = json.loads(result.stdout)
            relevant_certs = [
                c for c in certs 
                if c.get("managed", {}).get("domains") and hostname in c["managed"]["domains"]
            ]
            
            if not relevant_certs:
                return {"status": "NOT_FOUND"}
                
            cert = relevant_certs[0]
            return {
                "status": cert.get("managed", {}).get("status", "UNKNOWN"),
                "domain_status": cert.get("managed", {}).get("domainStatus", {}).get(hostname, "UNKNOWN")
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def get_dns_nameservers(self, project_id: str, zone_name: str = "apigee-dns") -> List[str]:
        import subprocess
        try:
            result = subprocess.run(
                ["gcloud", "dns", "managed-zones", "describe", zone_name, "--project", project_id, "--format=json"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            return data.get("nameServers", [])
        except Exception:
            return []

    def get_deny_policy(self, project_id: str, policy_name: str) -> Optional[Dict[str, Any]]:
        # TODO: Implement IAM Deny Policy lookup
        return None

    def check_permission(self, project_id: str, principal: str, permission: str) -> bool:
        # TODO: Implement permission check with Deny Policy awareness
        return True
