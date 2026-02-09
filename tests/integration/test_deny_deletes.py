import pytest
from pathlib import Path
from scripts.cli.config import ConfigLoader
from scripts.cli.commands.core import run_terraform

@pytest.mark.integration
def test_deny_deletes_enforcement(existing_org_project_id, tmp_path):
    """
    Integration Test: Verify IAM Deny Policy enforcement.
    
    Scenario:
    1. Bootstrap & Deploy Deny Policy (as User).
    2. Create a resource (fake_secret) as SA.
    3. Attempt to DELETE resource as SA -> Should FAIL (Deny Policy).
    4. Remove Deny Policy (as User).
    5. Delete resource as SA -> Should SUCCEED.
    6. Restore Deny Policy (as User).
    """
    
    # Setup Config in tmp_path (FLAT structure)
    tfvars_content = f"""
gcp_project_id          = "{existing_org_project_id}"
apigee_runtime_location = "us-central1"
apigee_analytics_region = "us-central1"
apigee_billing_type     = "PAYG"
control_plane_location  = "us"
"""
    (tmp_path / "terraform.tfvars").write_text(tfvars_content)
    
    # Load Config
    config = ConfigLoader.load(tmp_path)
    
    # Helper to run apply
    def apply(**kwargs):
        # We target ONLY the resources needed for the deny-deletes test
        # This allows us to run against existing projects without managing Orgs/Networks
        return run_terraform(
            config,
            "apply",
            auto_approve=True,
            targets=[
                "google_secret_manager_secret.fake_secret",
                "google_secret_manager_secret_version.fake_secret_v1"
            ],
            **kwargs
        )

    print(f"\n[Test] Target Project: {existing_org_project_id}")

    # Step 1: Bootstrap & Create Secret (Policy ON)
    # This runs bootstrap automatically if needed.
    print("Step 1: Create secret (Policy ON)...")
    # Note: Phase 0 (Bootstrap) handles Deny Policy creation. 
    # Phase 1 (Main) handles Secret creation.
    assert apply(fake_secret=True, deletes_allowed=False, skip_impersonation=False) == 0

    # Step 2: Try Delete (Policy ON) -> Should FAIL
    print("Step 2: Try Delete (Policy ON)...")
    # Setting fake_secret=False should trigger deletion of the secret
    assert apply(fake_secret=False, deletes_allowed=False, skip_impersonation=False) != 0

    # Step 3: Remove Policy (As User)
    print("Step 3: Remove Policy (As User)...")
    # We keep the secret (fake_secret=True) but allow deletes (deletes_allowed=True)
    # Phase 0 logic handles Deny Policy removal when deletes_allowed=True
    assert apply(fake_secret=True, deletes_allowed=True, skip_impersonation=True) == 0

    # Step 4: Delete Secret (Policy OFF) -> Should SUCCEED
    print("Step 4: Delete Secret (Policy OFF)...")
    assert apply(fake_secret=False, deletes_allowed=True, skip_impersonation=False) == 0

    # Step 5: Restore Policy (As User)
    print("Step 5: Restore Policy (As User)...")
    assert apply(fake_secret=False, deletes_allowed=False, skip_impersonation=True) == 0
