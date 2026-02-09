import subprocess
import json
import shutil
from typing import Optional
from .base import CloudProvider
from ..schemas import ApigeeProjectStatus
from ..mappers import map_state_to_status
from ..core import load_tfstate, get_project_paths

class TerraformCloudProvider(CloudProvider):
    """
    Implements CloudProvider using Terraform as the primary engine.
    Uses 'terraform refresh' to sync reality and state parsing for data.
    """

    def get_status(self, project_id: str) -> Optional[ApigeeProjectStatus]:
        """
        Syncs state and returns comprehensive status.
        """
        # Note: In this implementation, we assume we are running within a command 
        # that has already initialized/staged the environment or we use global state logic.
        
        # 1. Load current state
        state = load_tfstate()
        if not state:
            return None
            
        # 2. Map to Pydantic
        return map_state_to_status(state)

    def get_project_id_by_label(self, label_key: str, label_value: str) -> Optional[str]:
        """Discovery still uses gcloud since Terraform doesn't do ad-hoc discovery well."""
        try:
            result = subprocess.run(
                ["gcloud", "projects", "list", f"--filter=labels.{label_key}:{label_value}", "--format=value(projectId)", "--limit=1"],
                capture_output=True, text=True
            )
            return result.stdout.strip() or None
        except:
            return None
