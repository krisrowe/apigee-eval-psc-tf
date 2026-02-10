import json
import pytest
import subprocess
from pathlib import Path
from click.testing import CliRunner
from scripts.cli.app import cli
from scripts.cli.paths import get_state_path

@pytest.mark.integration
@pytest.mark.timeout(600)
def test_import_apply_with_template_no_state_partial_cloud_adoption_fill_blanks(ephemeral_project, tmp_path):
    """
    JOURNEY: Brownfield Adoption + Convergence.
    1. Pre-seed a VPC Network in the cloud (simulate existing infra).
    2. Run `apim import`. It should adopt the Network.
    3. Run `apim apply --skip-apigee`. 
    4. Verify the final state contains BOTH the adopted Network AND the newly enabled APIs.
    """
    # 1. Pre-Seed Network
    print(f"Enabling Compute API in {ephemeral_project}...")
    subprocess.run([
        "gcloud", "services", "enable", "compute.googleapis.com",
        "--project", ephemeral_project,
        "--quiet"
    ], check=True)
    
    # Wait for API propagation
    import time
    time.sleep(10)

    print(f"Pre-seeding network in {ephemeral_project}...")
    subprocess.run([
        "gcloud", "compute", "networks", "create", "apigee-network",
        "--project", ephemeral_project,
        "--subnet-mode", "auto",
        "--quiet"
    ], check=True)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 2. Run Import
        result_import = runner.invoke(cli, ["import", ephemeral_project])
        
        if result_import.exit_code != 0:
            print(result_import.output)
            
        assert result_import.exit_code == 0
        assert "Imported google_compute_network.apigee_network" in result_import.output

        # 3. Run Apply (Fill in blanks)
        # Use a template to define the desired state for APIs and regions
        template = {
            "billing_type": "PAYG",
            "runtime_location": "us-central1",
            "analytics_region": "us-central1"
        }
        tpl_path = Path(tmp_path) / "tpl.json"
        tpl_path.write_text(json.dumps(template))

        # This runs FOR REAL but skips heavy bits. It should enable APIs.
        result_apply = runner.invoke(cli, ["apply", str(tpl_path.absolute()), "--skip-apigee"])
        
        if result_apply.exit_code != 0:
            print(result_apply.output)
            
        assert result_apply.exit_code == 0
        assert "✓ System Converged" in result_apply.output

        # 4. Final State Verification
        state_path = get_state_path(ephemeral_project, phase="1-main")
        assert state_path.exists()
        
        with open(state_path, "r") as f:
            state = json.load(f)
            
        resource_types = [r["type"] for r in state.get("resources", [])]
        
        # Must have the adopted VPC
        assert "google_compute_network" in resource_types
        # Must have the filled-in APIs
        assert "google_project_service" in resource_types
