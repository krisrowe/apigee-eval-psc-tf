import pytest
import os
import shutil
from pathlib import Path
from scripts.cli.cloud.factory import set_cloud_provider
from scripts.cli.cloud.mock import MockCloudProvider

@pytest.fixture(scope="session", autouse=True)
def isolate_state_dir(tmp_path_factory):
    """
    Sets APIGEE_TF_DATA_DIR to a temporary directory for the unit test session.
    Prevents pollution of the user's actual ~/.local/share/apigee-tf directory.
    """
    temp_dir = tmp_path_factory.mktemp("apigee_tf_data")
    os.environ["APIGEE_TF_DATA_DIR"] = str(temp_dir)
    yield temp_dir
    if "APIGEE_TF_DATA_DIR" in os.environ:
        del os.environ["APIGEE_TF_DATA_DIR"]

@pytest.fixture
def cloud_provider():
    """
    Fresh MockCloudProvider for each test.
    """
    mock = MockCloudProvider()
    set_cloud_provider(mock)
    yield mock
    set_cloud_provider(None)
