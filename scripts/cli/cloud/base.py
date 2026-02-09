from abc import ABC, abstractmethod
from typing import Optional
from ..schemas import ApigeeProjectStatus

class CloudProvider(ABC):
    """
    Abstract interface for Apigee Cloud operations.
    """

    @abstractmethod
    def get_status(self, project_id: str) -> Optional[ApigeeProjectStatus]:
        """Fetch the comprehensive status of the Apigee Project."""
        pass

    @abstractmethod
    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        """Lookup GCP Project ID by a specific label (Discovery)."""
        pass