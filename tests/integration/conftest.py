import pytest
import os
import warnings
import subprocess
import shutil
from pathlib import Path

def pytest_collection_modifyitems(items):
    """
    Apply a 300-second timeout to all integration tests.
    """
    for item in items:
        item.add_marker(pytest.mark.timeout(300))




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

import random
import string

@pytest.fixture(scope="function", autouse=True)
def isolated_dirs(tmp_path):
    """
    Automatically isolates each test execution into a temporary data/cache directory.
    This prevents tests from polluting ~/.local/share/apigee-tf or ~/.cache/apigee-tf.
    """
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    data_dir.mkdir()
    cache_dir.mkdir()
    
    # Set Env Vars
    os.environ["APIGEE_TF_DATA_DIR"] = str(data_dir)
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    
    yield
    
    # Cleanup (Env vars persist in process, so we must unset/reset)
    del os.environ["APIGEE_TF_DATA_DIR"]
    del os.environ["XDG_CACHE_HOME"]

import logging

logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def billing_account_id():
    """
    Finds a valid Billing Account ID by looking up a project labeled 'apigee-tf=integration-testing'.
    """
    gcloud = shutil.which("gcloud")
    logger.debug(f"gcloud path: {gcloud}")
    
    if not gcloud:
        logger.debug("gcloud binary not found via shutil.which")
        return None

    try:
        # 1. Find the project
        cmd = [
            gcloud, "projects", "list",
            "--filter", "labels.apigee-tf=integration-testing",
            "--format", "value(projectId)",
            "--limit", "1"
        ]
        logger.debug(f"Running discovery: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        logger.debug(f"Discovery RC: {res.returncode}")
        logger.debug(f"Discovery STDOUT: {res.stdout}")
        logger.debug(f"Discovery STDERR: {res.stderr}")
        
        pid = res.stdout.strip()
        
        if pid:
            # 2. Get the billing account
            cmd = [
                gcloud, "beta", "billing", "projects", "describe", pid,
                "--format", "value(billingAccountName)"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            logger.debug(f"Billing RC: {res.returncode}")
            logger.debug(f"Billing STDOUT: {res.stdout}")
            
            # format: billingAccounts/XXXX-XXXX-XXXX
            if res.returncode == 0 and res.stdout.strip():
                acct = res.stdout.strip().split("/")[-1]
                logger.debug(f"Found Billing Account: {acct}")
                return acct
    except Exception as e:
        logger.debug(f"Exception during discovery: {e}")
        pass
        
    return os.environ.get("GOOGLE_BILLING_ACCOUNT_ID")

@pytest.fixture
def ephemeral_project(billing_account_id):
    """
    Creates a fresh, temporary GCP project and links billing.
    Yields the project_id, then deletes it on teardown.
    """
    if not billing_account_id:
        pytest.skip("No Billing Account found (label 'apigee-tf=integration-testing' or GOOGLE_BILLING_ACCOUNT_ID).")

    gcloud = shutil.which("gcloud")
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    project_id = f"apigee-tf-ci-{suffix}"
    
    print(f"\n[Fixture] Creating ephemeral project: {project_id}")
    
    try:
        # 1. Create Project
        subprocess.run([gcloud, "projects", "create", project_id, "--quiet"], check=True)
        
        # 2. Link Billing
        subprocess.run([
            gcloud, "billing", "projects", "link", project_id, 
            f"--billing-account={billing_account_id}", "--quiet"
        ], check=True)
        
        yield project_id
        
    finally:
        print(f"\n[Fixture] Tearing down project: {project_id}")
        subprocess.run([gcloud, "projects", "delete", project_id, "--quiet"], check=False)


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
