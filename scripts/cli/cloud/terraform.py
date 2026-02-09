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
        # Resolve state path for the given project_id
        # TODO: Get Data Dir from env/config properly (duplication)
        import os
        from pathlib import Path
        
        data_home = os.environ.get("APIGEE_TF_DATA_DIR")
        if data_home:
            root = Path(data_home)
        else:
            root = Path.home() / ".local/share/apigee-tf"
            
        # Check 1-main state
        state_file = root / project_id / "tf" / "1-main" / "terraform.tfstate"
        
        if not state_file.exists():
            return None
            
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            return map_state_to_status(state)
        except json.JSONDecodeError:
            return None

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
