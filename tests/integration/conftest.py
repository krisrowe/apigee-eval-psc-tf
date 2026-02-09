import pytest
import os
import warnings
import subprocess
import shutil
from pathlib import Path

def pytest_collection_modifyitems(items):
    """
    Apply a 20-second timeout to all integration tests.
    """
    for item in items:
        item.add_marker(pytest.mark.timeout(20))




def _discover_project_by_label(label_filter):
    """
    Helper to find a project with a specific label.
    """
    gcloud = shutil.which("gcloud")
    if not gcloud:
        return None
        
    try:
        # gcloud projects list --filter="labels.apigee-tf=integration-test" --format="value(projectId)" --limit=1
        cmd = [
            gcloud, "projects", "list",
            "--filter", label_filter,
            "--format", "value(projectId)",
            "--limit", "1"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return None

@pytest.fixture(scope="session")
def existing_org_project_id():
    """
    Returns a Project ID that ALREADY has an Apigee Org.
    Source:
    1. Env Var: EXISTING_APIGEE_ORG_PROJECT_ID
    2. Label: apigee-tf=integration-test
    """
    pid = os.environ.get("EXISTING_APIGEE_ORG_PROJECT_ID")
    if not pid:
        pid = _discover_project_by_label("labels.apigee-tf=integration-test")
        
    if not pid:
        warnings.warn("EXISTING_APIGEE_ORG_PROJECT_ID not set and no project found with label 'apigee-tf=integration-test'. Skipping related integration tests.")
        pytest.skip("No Existing Org Project found", allow_module_level=True)
    
    print(f"\n[Integration] Using Existing Org Project: {pid}")
    return pid

@pytest.fixture(scope="session")
def no_org_project_id():
    """
    Returns a Project ID that DOES NOT have an Apigee Org (but has billing/APIs).
    Source:
    1. Env Var: NO_APIGEE_ORG_PROJECT_ID
    2. Label: apigee-tf=missing
    """
    pid = os.environ.get("NO_APIGEE_ORG_PROJECT_ID")
    if not pid:
        pid = _discover_project_by_label("labels.apigee-tf=missing")

    if not pid:
        warnings.warn("NO_APIGEE_ORG_PROJECT_ID not set and no project found with label 'apigee-tf=missing'. Skipping related integration tests.")
        pytest.skip("No Empty Project found", allow_module_level=True)
        
    print(f"\n[Integration] Using No Org Project: {pid}")
    return pid
