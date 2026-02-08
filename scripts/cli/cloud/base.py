from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class CloudProvider(ABC):
    """
    Abstract interface for Apigee Cloud operations.
    """

    @abstractmethod
    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Apigee Organization details."""
        pass

    @abstractmethod
    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        """Lookup GCP Project ID by a specific label."""
        pass

    @abstractmethod
    def list_instances(self, org_id: str) -> List[Dict[str, Any]]:
        """List Apigee Instances."""
        pass

    @abstractmethod
    def list_envgroups(self, org_id: str) -> List[Dict[str, Any]]:
        """List Apigee Environment Groups."""
        pass

    @abstractmethod
    def get_environments(self, org_id: str) -> List[str]:
        """List Apigee Environments names."""
        pass

    @abstractmethod
    def get_ssl_certificate_status(self, project_id: str, hostname: str) -> Dict[str, Any]:
        """Fetch Google-managed SSL certificate status."""
        pass

    @abstractmethod
    def get_dns_nameservers(self, project_id: str, zone_name: str = "apigee-dns") -> List[str]:
        """Fetch assigned name servers for a GCP managed DNS zone."""
        pass

    @abstractmethod
    def get_deny_policy(self, project_id: str, policy_name: str) -> Optional[Dict[str, Any]]:
        """[Phase 2] Fetch a IAM Deny Policy by name."""
        pass

    @abstractmethod
    def check_permission(self, project_id: str, principal: str, permission: str) -> bool:
        """[Phase 2] Verify if a specific principal has a permission (accounting for Deny)."""
        pass
