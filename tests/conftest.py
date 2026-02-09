import pytest
import os
import shutil
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def isolate_state_dir(tmp_path_factory):
    """
    Sets APIGEE_TF_DATA_DIR to a temporary directory for the entire test session.
    Prevents pollution of the user's actual ~/.local/share/apigee-tf directory.
    This applies to BOTH unit and integration tests.
    """
    temp_dir = tmp_path_factory.mktemp("apigee_tf_data")
    os.environ["APIGEE_TF_DATA_DIR"] = str(temp_dir)
    print(f"\n[Global] Isolated State Dir: {temp_dir}")
    yield temp_dir
    if "APIGEE_TF_DATA_DIR" in os.environ:
        del os.environ["APIGEE_TF_DATA_DIR"]
