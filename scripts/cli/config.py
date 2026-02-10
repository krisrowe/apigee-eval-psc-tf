import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

import hcl2
from scripts.cli.config_sdk import get_config_manager

logger = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:
    import tomli as tomllib

@dataclass
class ProjectConfig:
    name: str
    gcp_project_id: str
    region: str

@dataclass
class ApigeeConfig:
    billing_type: Optional[str] = None  # Smart Default: EVALUATION, auto-upgrades to PAYG for DRZ
    analytics_region: str = "us-central1"
    control_plane_location: str = ""
    consumer_data_region: str = ""
    instance_name: Optional[str] = None
    state_suffix: Optional[str] = None  # For isolating multiple deployments in same project

@dataclass
class NetworkConfig:
    domain: Optional[str] = None

@dataclass
class Config:
    project: ProjectConfig
    apigee: ApigeeConfig
    network: NetworkConfig
    root_dir: Path

class ConfigLoader:
    # Supported config filenames in order of preference
    CONFIG_FILES = ["terraform.tfvars"]

    @classmethod
    def load(cls, working_dir: Path, optional: bool = False) -> Config:
        logger.debug(f"Loading config from: {working_dir}")
        # Enforce policy: apigee.tfvars is forbidden
        legacy_file = working_dir / "apigee.tfvars"
        if legacy_file.exists():
             raise ValueError(f"Forbidden configuration file found: {legacy_file.name}. Please rename to 'terraform.tfvars' and ensure it contains standard HCL (e.g., gcp_project_id = \"...\").")

        hcl_path = None
        for filename in cls.CONFIG_FILES:
            candidate = working_dir / filename
            logger.debug(f"  Probing: {candidate}")
            if candidate.exists():
                hcl_path = candidate
                logger.debug(f"  Found: {hcl_path}")
                break
        
        data = {}
        if hcl_path:
            try:
                with open(hcl_path, "r") as f:
                    data = hcl2.load(f)
            except Exception as e:
                raise ValueError(f"Failed to parse {hcl_path.name}: {e}")
        elif not optional:
            logger.debug("  No config file found.")
            raise FileNotFoundError(f"Configuration file not found. Expected: {', '.join(cls.CONFIG_FILES)}")

        # Use the centralized ConfigManager for global settings
        sdk_config = get_config_manager().load()

        # HCL parser returns lists for blocks, we need to flatten if necessary
        def get_section(name):
            section = data.get(name, {})
            if isinstance(section, list) and len(section) > 0:
                return section[0]
            return section

        # Helper to get value from either        # Helper to get value
        def get_val(section, key, flat_key=None, default=None):
            # 1. Try nested block (TOML style): section { key = val }
            if section in data:
                sec_data = data[section]
                if isinstance(sec_data, list) and len(sec_data) > 0:
                    val = sec_data[0].get(key)
                    if val is not None: return val
                elif isinstance(sec_data, dict):
                    val = sec_data.get(key)
                    if val is not None: return val
            
            # 2. Try flat key (TFVARS style): flat_key = val
            if flat_key and flat_key in data:
                return data[flat_key]
            
            # 3. Fallback to just key (if flat_key not provided or match)
            if key in data:
                return data[key]
                
            return default

        project_id = get_val("project", "gcp_project_id", "gcp_project_id") or os.environ.get("GCP_PROJECT_ID", "")
        region = get_val("project", "region", "apigee_runtime_location") or os.environ.get("GCP_REGION", "us-central1")
        name = get_val("project", "name", default=project_id or "unnamed-project")
        
        # Smart Defaulting for Billing
        control_plane = get_val("apigee", "control_plane_location", "control_plane_location", "")
        billing_type = get_val("apigee", "billing_type", "apigee_billing_type")
        if not billing_type:
            billing_type = "PAYG" if control_plane else "EVALUATION"

        return Config(
            project=ProjectConfig(
                name=name,
                gcp_project_id=project_id,
                region=region,
            ),
            apigee=ApigeeConfig(
                billing_type=billing_type,
                analytics_region=get_val("apigee", "analytics_region", "apigee_analytics_region", "us-central1"),
                control_plane_location=control_plane,
                consumer_data_region=get_val("apigee", "consumer_data_region", "consumer_data_region", ""),
                instance_name=get_val("apigee", "instance_name", "apigee_instance_name"),
                state_suffix=get_val("apigee", "state_suffix", "state_suffix"),
            ),
            network=NetworkConfig(
                domain=get_val("network", "domain", "domain_name")
            ),
            root_dir=working_dir.resolve()
        )

    @classmethod
    def find_root(cls) -> Path:
        """Looks for config file (HCL) in CWD and parents."""
        cwd = Path.cwd()
        current = cwd
        logger.debug(f"Searching for workspace root from: {cwd}")
        while True:
            for filename in cls.CONFIG_FILES:
                candidate = current / filename
                logger.debug(f"  Checking: {candidate}")
                if candidate.exists():
                    logger.debug(f"  Root found: {current}")
                    return current
            
            if current.parent == current:  # Reached root
                break
            current = current.parent
            
        raise FileNotFoundError(f"Could not find configuration file ({', '.join(cls.CONFIG_FILES)}) in {cwd} or parents.")
