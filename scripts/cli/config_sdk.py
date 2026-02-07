"""
Centralized configuration management SDK for Apigee Terraform CLI.

This module provides strongly-typed access to CLI configuration settings
stored in ~/.config/apigee-tf/settings.json.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class CliConfig:
    """Strongly-typed configuration settings."""
    default_root_domain: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CliConfig':
        """Create CliConfig from dictionary, ignoring unknown keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class ConfigManager:
    """Manages CLI configuration with strongly-typed access."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config manager.
        
        Args:
            config_dir: Optional custom config directory. 
                       Defaults to ~/.config/apigee-tf
        """
        if config_dir is None:
            config_dir = Path.home() / '.config' / 'apigee-tf'
        
        self.config_dir = config_dir
        self.settings_file = config_dir / 'settings.json'
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> CliConfig:
        """Load configuration from disk."""
        if not self.settings_file.exists():
            return CliConfig()
        
        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
            return CliConfig.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return CliConfig()
    
    def save(self, config: CliConfig) -> None:
        """Save configuration to disk."""
        with open(self.settings_file, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)
    
    def get(self, key: str) -> Optional[Any]:
        """Get a specific configuration value."""
        config = self.load()
        return getattr(config, key, None)
    
    def set(self, key: str, value: Any) -> None:
        """Set a specific configuration value."""
        config = self.load()
        if hasattr(config, key):
            setattr(config, key, value)
            self.save(config)
        else:
            raise ValueError(f"Unknown configuration key: {key}")
    
    def reset(self) -> None:
        """Clear all configuration."""
        self.save(CliConfig())
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as dictionary."""
        return self.load().to_dict()


# Global instance for convenience
_default_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the default ConfigManager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConfigManager()
    return _default_manager
