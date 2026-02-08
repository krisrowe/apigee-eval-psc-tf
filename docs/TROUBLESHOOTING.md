# Troubleshooting: Common Apigee Terraform Errors

## 1. Deny Policy Permission Denied (403)
**Error:** `Error creating DenyPolicy: googleapi: Error 403: Permission iam.googleapis.com/denypolicies.create denied`

**Cause:** Creating IAM Deny Policies requires high-level permissions on the Project (or Folder/Org). Standard "Owner" role usually suffices, but ensure you have `iam.denypolicies.create`.

**Solution:**
Ensure your user account has the **Project Owner** or **IAM Deny Admin** role on the target project.
