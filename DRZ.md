# Apigee Data Residency (DRZ) - Canada Findings

This document tracks technical findings, API behaviors, and HCL alignment strategies for Apigee X deployments in the Canada jurisdiction (`ca`).

## Official Documentation References

*   **Jurisdictions**: Canada is identified as the `ca` jurisdiction. [Apigee Locations](https://cloud.google.com/apigee/docs/locations#available-apigee-api-control-plane-regions)
*   **DRZ Concepts**: `analytics_region` is officially **deprecated** for DRZ-enabled organizations. High-volume consumer data (analytics) is stored in the `CONSUMER_DATA_REGION`. [Introduction to Data Residency](https://cloud.google.com/apigee/docs/api-platform/get-started/drz-concepts)
*   **Service Endpoints**: Jurisdictional organizations must use regional endpoints like `https://ca-apigee.googleapis.com` for management API calls. [DRZ Service Endpoints](https://cloud.google.com/apigee/docs/api-platform/get-started/drz-concepts#drz-service-endpoint)

## Observed API Behavior (Canada Jurisdictions)

When an Apigee Organization is provisioned with `control_plane_location = "ca"` and `api_consumer_data_location = "northamerica-northeast1"`, the legacy `analyticsRegion` field is suppressed (returned as `""`) in the API response.

### Terraform Impact
Terraform's `google_apigee_organization` resource treats `analytics_region` as a `ForceNew` field. This mismatch between HCL and the suppressed API field triggers a destructive plan.

## Technical Proof (Live API Response)

Direct `curl` output from `https://ca-apigee.googleapis.com/v1/organizations/target-project-id`:

```json
{
  "name": "target-project-id",
  "projectId": "target-project-id",
  "state": "ACTIVE",
  "billingType": "PAYG",
  "apiConsumerDataLocation": "northamerica-northeast1",
  "runtimeType": "CLOUD",
  "subscriptionType": "PAID"
  // Note: analyticsRegion is absent here
}
```

## HCL Alignment Strategy

To avoid destructive "Ghost Changes" while maintaining a single HCL for both Global and DRZ environments:

```hcl
resource "google_apigee_organization" "apigee_org" {
  project_id       = var.gcp_project_id
  # Logic: If control_plane_location is set (DRZ), pass empty string to match API.
  analytics_region = var.control_plane_location != "" ? "" : var.apigee_analytics_region
  
  api_consumer_data_location = var.control_plane_location != "" ? var.apigee_analytics_region : null
  # ...
}
```

## Infrastructure Lessons Learned

### 1. Networking (Fresh Projects)
*   Fresh projects may lack a `default` VPC.
*   **Action**: Always provision an explicit VPC (`google_compute_network`) and pass it to the PSC NEG.

### 2. Ingress & PSC NEGs
*   **Issue**: `Invalid value for field 'resource.healthChecks': ''`.
*   **Reason**: Backend Services using Private Service Connect (PSC) NEGs **must not** have a health check configured at the Backend Service level. Health monitoring is internal to the PSC service attachment.
*   **Fix**: Omit `health_checks` from the `google_compute_backend_service` if the backend is a PSC NEG.
