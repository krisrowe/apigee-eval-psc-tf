from typing import Optional
from .base import CloudProvider

_provider: Optional[CloudProvider] = None

def get_cloud_provider() -> CloudProvider:
    """Get the current cloud provider."""
    global _provider
    if _provider is None:
        from .terraform import TerraformCloudProvider
        _provider = TerraformCloudProvider()
    return _provider

def set_cloud_provider(provider: Optional[CloudProvider]) -> None:
    """Set the cloud provider (used for testing)."""
    global _provider
    _provider = provider