import pytest
import tempfile
import json
from pathlib import Path
from scripts.cli.schemas import ApigeeOrgTemplate, SchemaValidationError

def test_template_valid_standard():
    """Validates a standard (non-DRZ) template."""
    tmpl = ApigeeOrgTemplate(
        billing_type="EVALUATION",
        drz=False,
        runtime_location="us-central1",
        analytics_region="us-central1"
    )
    tmpl.validate() # Should not raise

def test_template_valid_drz():
    """Validates a valid DRZ template."""
    tmpl = ApigeeOrgTemplate(
        billing_type="PAYG",
        drz=True,
        runtime_location="northamerica-northeast1",
        control_plane_location="ca",
        consumer_data_region="northamerica-northeast1"
    )
    tmpl.validate() # Should not raise

def test_drz_requires_payg_or_subscription():
    """DRZ cannot use EVALUATION billing."""
    tmpl = ApigeeOrgTemplate(
        billing_type="EVALUATION",
        drz=True,
        runtime_location="ca-central1",
        control_plane_location="ca",
        consumer_data_region="ca-central1"
    )
    with pytest.raises(SchemaValidationError, match="cannot be 'EVALUATION'"):
        tmpl.validate()

def test_drz_excludes_analytics_region():
    """DRZ must NOT set analytics_region."""
    tmpl = ApigeeOrgTemplate(
        drz=True,
        billing_type="PAYG",
        runtime_location="ca",
        control_plane_location="ca",
        consumer_data_region="ca",
        analytics_region="us-central1" # Fail
    )
    with pytest.raises(SchemaValidationError, match="'analytics_region' must NOT be set"):
        tmpl.validate()

def test_standard_excludes_drz_fields():
    """Standard mode must NOT set DRZ fields."""
    tmpl = ApigeeOrgTemplate(
        drz=False,
        runtime_location="us-central1",
        analytics_region="us-central1",
        control_plane_location="ca" # Fail
    )
    with pytest.raises(SchemaValidationError, match="DRZ fields .* are not allowed"):
        tmpl.validate()

def test_unknown_fields_rejected():
    """JSON with unknown fields should raise SchemaValidationError."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump({
            "runtime_location": "us-central1",
            "analytics_region": "us-central1",
            "mumbo_jumbo": "invalid"
        }, f)
        path = f.name
        
    try:
        with pytest.raises(SchemaValidationError, match="Unknown fields"):
            ApigeeOrgTemplate.from_json_file(path)
    finally:
        Path(path).unlink()

def test_to_tfvars_conversion():
    """Verifies HCL generation."""
    tmpl = ApigeeOrgTemplate(
        billing_type="PAYG",
        drz=True,
        runtime_location="loc-1",
        control_plane_location="cp-1",
        consumer_data_region="cdr-1",
        instance_name="my-inst"
    )
    tfvars = tmpl.to_tfvars("my-proj")
    
    assert 'gcp_project_id = "my-proj"' in tfvars
    assert 'apigee_billing_type = "PAYG"' in tfvars
    assert 'control_plane_location = "cp-1"' in tfvars
    assert 'consumer_data_region = "cdr-1"' in tfvars
    assert 'apigee_instance_name = "my-inst"' in tfvars
