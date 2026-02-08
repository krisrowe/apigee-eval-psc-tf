import pytest
from scripts.cli.cloud.factory import set_cloud_provider
from scripts.cli.cloud.mock import MockCloudProvider

@pytest.fixture
def cloud_provider():
    """
    Fresh MockCloudProvider for each test.
    """
    mock = MockCloudProvider()
    set_cloud_provider(mock)
    yield mock
    set_cloud_provider(None)
