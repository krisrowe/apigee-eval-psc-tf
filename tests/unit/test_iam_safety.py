import pytest
from scripts.cli.cloud.mock import MockCloudProvider

def test_deny_policy_blocks_admin_group():
    """Verify that a Deny Policy correctly blocks an Admin Group despite having Allow roles."""
    provider = MockCloudProvider()
    project_id = "test-project"
    admin_group = "group:apigee-admins@example.com"
    deployer_sa = "serviceAccount:deployer-sa@example.com"
    permission = "apigee.organizations.delete"

    # 1. Setup Allow Permissions (Admin Group has delete permission)
    provider.permissions[admin_group] = [permission]
    
    # 2. Setup Deny Policy blocking the Admin Group but exempting the Deployer
    provider.deny_policies["test-project/protect-org"] = {
        "rules": [
            {
                "deny_rule": {
                    "denied_principals": [admin_group],
                    "denied_permissions": [permission],
                    "exception_principals": [deployer_sa]
                }
            }
        ]
    }

    # 3. Assertions
    # Admin should be BLOCKED (Deny wins)
    assert provider.check_permission(project_id, admin_group, permission) is False, \
        "Admin group should be blocked by Deny Policy"

    # Deployer should be ALLOWED (Exception bypassed Deny)
    # Note: Deployer also needs an Allow role to pass the final check
    provider.permissions[deployer_sa] = [permission]
    assert provider.check_permission(project_id, deployer_sa, permission) is True, \
        "Deployer should be allowed via Exception"

def test_deny_policy_bypass_for_unrelated_principal():
    """Principals not in the Deny list should only be subject to Allow roles."""
    provider = MockCloudProvider()
    project_id = "test-project"
    random_user = "user:stranger@example.com"
    permission = "apigee.organizations.delete"

    provider.deny_policies["test-project/protect-org"] = {
        "rules": [{
            "deny_rule": {
                "denied_principals": ["group:someone-else"],
                "denied_permissions": [permission]
            }
        }]
    }

    # No allow role -> False
    assert provider.check_permission(project_id, random_user, permission) is False
    
    # Give allow role -> True (not in Deny list)
    provider.permissions[random_user] = [permission]
    assert provider.check_permission(project_id, random_user, permission) is True
