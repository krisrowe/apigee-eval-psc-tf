import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib

@dataclass
class ProjectConfig:
    name: str
    gcp_project_id: str
    region: str
    nickname: str

@dataclass
class ApigeeConfig:
    billing_type: str = "PAYG"
    analytics_region: str = "us-central1"
    control_plane_location: str = ""
    consumer_data_region: str = ""

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
    CONFIG_FILE = "apigee.toml"

    @classmethod
    def load(cls, working_dir: Path) -> Config:
        config_path = working_dir / cls.CONFIG_FILE
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse {cls.CONFIG_FILE}: {e}")

        project_data = data.get("project", {})
        apigee_data = data.get("apigee", {})
        network_data = data.get("network", {})

        return Config(
            project=ProjectConfig(
                name=project_data.get("name", "unnamed-project"),
                gcp_project_id=project_data.get("gcp_project_id", ""),
                region=project_data.get("region", "us-central1"),
                nickname=project_data.get("nickname", project_data.get("name", "unnamed")),
            ),
            apigee=ApigeeConfig(
                billing_type=apigee_data.get("billing_type", "PAYG"),
                analytics_region=apigee_data.get("analytics_region", "us-central1"),
                control_plane_location=apigee_data.get("control_plane_location", ""),
                consumer_data_region=apigee_data.get("consumer_data_region", ""),
            ),
            network=NetworkConfig(
                domain=network_data.get("domain"),
            ),
            root_dir=working_dir.resolve()
        )

    @classmethod
    def find_root(cls) -> Path:
        """Looks for apigee.toml in CWD and parents."""
        cwd = Path.cwd()
        for path in [cwd] + list(cwd.parents):
            if (path / cls.CONFIG_FILE).exists():
                return path
        raise FileNotFoundError(f"Could not find {cls.CONFIG_FILE} in {cwd} or parents.")
