"""Template validation and loading for import command."""
import json
from typing import Dict, Any, Optional
from pathlib import Path


VALID_FIELDS = {
    "gcp_project_id",
    "domain_name",
    "apigee_analytics_region",
    "apigee_runtime_location",
    "control_plane_location",
    "project_nickname"
}


def validate_template(data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Validate template using stdlib only.
    
    Args:
        data: Template data as dict
        
    Returns:
        Validated template dict
        
    Raises:
        ValueError: If template is invalid
    """
    if not isinstance(data, dict):
        raise ValueError("Template must be a JSON object")
    
    for key, value in data.items():
        if key not in VALID_FIELDS:
            raise ValueError(f"Unknown field '{key}'. Valid fields: {', '.join(sorted(VALID_FIELDS))}")
        
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Field '{key}' must be a string or null, got {type(value).__name__}")
    
    return data


def load_template(template_path: str) -> Dict[str, Optional[str]]:
    """
    Load and validate a template file.
    
    Args:
        template_path: Path to template JSON file
        
    Returns:
        Validated template dict
        
    Raises:
        FileNotFoundError: If template file doesn't exist
        ValueError: If template is invalid
        json.JSONDecodeError: If template is not valid JSON
    """
    path = Path(template_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    return validate_template(data)
