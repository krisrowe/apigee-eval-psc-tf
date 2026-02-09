import logging
import shutil
import os
from pathlib import Path
from rich.console import Console
from scripts.cli.config import Config
from scripts.cli.paths import get_cache_dir, get_state_path

logger = logging.getLogger(__name__)
console = Console()

class TerraformStager:
    def __init__(self, config: Config):
        self.config = config
        self.project_root = config.root_dir
        # Package root is 3 levels up from scripts/cli/engine.py
        self.package_root = Path(__file__).parent.parent.parent.resolve()
        
        # Staging Directory: <CACHE_DIR>/<project_id>[/<suffix>]
        # Ephemeral: Can be wiped at any time.
        self.staging_dir = get_cache_dir() / config.project.gcp_project_id
        if config.apigee.state_suffix:
            self.staging_dir = self.staging_dir / config.apigee.state_suffix

    def resolve_template_path(self, path_str: str) -> Path:
        """
        Resolves a template file path (.json) using the priority:
        1. Absolute/Explicit Path
        2. CWD/<path>
        3. CWD/templates/<path>
        4. Package/templates/<path>
        
        Appends .json if missing.
        """
        if not path_str.endswith(".json"):
            path_str += ".json"
            
        return self._resolve_file(path_str, "templates", "Template")

    def resolve_config_path(self, path_str: str) -> Path:
        """
        Resolves a config file path (.tfvars) using the priority:
        1. Absolute/Explicit Path
        2. CWD/<path>
        3. CWD/templates/<path> (Renamed from config)
        4. Package/templates/<path>
        """
        return self._resolve_file(path_str, "templates", "Config")

    def _resolve_file(self, path_str: str, search_dir: str, type_label: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            logger.debug(f"Checking absolute path: {p}")
            if not p.exists():
                logger.debug(f"NOT FOUND: {p}")
                raise FileNotFoundError(f"{type_label} file not found: {p}")
            logger.debug(f"FOUND: {p}")
            return p

        # Search Paths
        candidates = [
            self.project_root / path_str,
            self.project_root / search_dir / path_str,
            self.package_root / search_dir / path_str
        ]

        for candidate in candidates:
            logger.debug(f"Checking candidate: {candidate}")
            if candidate.exists():
                logger.debug(f"FOUND: {candidate}")
                return candidate
            else:
                logger.debug(f"NOT FOUND: {candidate}")
        
        logger.error(f"{type_label} '{path_str}' not found in any search path.")
        raise FileNotFoundError(f"{type_label} '{path_str}' not found in: {[str(c) for c in candidates]}")

    def stage_phase(self, phase_name: str, config_files: list[str] = None) -> Path:
        """
        Stages a specific phase folder (e.g. '0-bootstrap', '1-main').
        Returns path to the staged directory for that phase.
        We stage into 'tf/<phase_name>' to preserve relative paths if needed, 
        but modules are now copied directly inside.
        """
        phase_staging = self.staging_dir / "tf" / phase_name
        console.print(f"[dim]Staging {phase_name} in {phase_staging}...[/dim]")
        
        if not phase_staging.exists():
            phase_staging.mkdir(parents=True)
            
        # 1. WIPE
        self._wipe_dir(phase_staging)
        
        # 2. COPY PACKAGE TF (from tf/<phase_name>)
        self._copy_phase_tf(phase_name, phase_staging)
        
        # 3. COPY SHARED MODULES (to phase_staging/modules)
        self._copy_shared_modules(phase_staging)
        
        # 4. GENERATE BACKEND (unique state file per phase)
        self._generate_backend(phase_name, phase_staging)
        
        # 5. GENERATE TFVARS (Bridge Config Object -> Flat TF Vars)
        self._generate_tfvars(phase_staging)
        
        # 6. COPY USER FILES (overlay)
        self._copy_user_files(phase_staging)
        
        # 7. INJECT EXPLICT CONFIGS (--config)
        if config_files:
            self._inject_configs(phase_staging, config_files)

        return phase_staging

    def _wipe_dir(self, target_dir: Path):
        """Standard wipe that preserves the directory itself if needed, but shutil.rmtree is cleaner."""
        if target_dir.exists():
            # We recreate it to be clean
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

    def _copy_phase_tf(self, phase_name: str, target_dir: Path):
        source_dir = self.package_root / "tf" / phase_name
        if not source_dir.exists():
             raise FileNotFoundError(f"Terraform phase module not found: {source_dir}")
             
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    def _copy_shared_modules(self, target_dir: Path):
        """Copies shared modules into the phase directory (./modules)."""
        src_modules = self.package_root / "modules"
        dest_modules = target_dir / "modules"
        
        if src_modules.exists():
            if dest_modules.exists():
                shutil.rmtree(dest_modules)
            shutil.copytree(src_modules, dest_modules)

    def _generate_backend(self, phase_name: str, target_dir: Path):
        """Generates a local backend configuration."""
        # Use centralized path logic
        state_path = get_state_path(
            self.config.project.gcp_project_id, 
            phase=phase_name, 
            suffix=self.config.apigee.state_suffix
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        
        backend_config = f'''
terraform {{
  backend "local" {{
    path = "{state_path}"
  }}
}}
'''
        (target_dir / "backend.tf").write_text(backend_config)

    def _generate_tfvars(self, target_dir: Path):
        """Generates auto.tfvars.json in target_dir."""
        import json
        tfvars_content = {
            "gcp_project_id": self.config.project.gcp_project_id,
            "apigee_runtime_location": self.config.project.region,
            "apigee_analytics_region": self.config.apigee.analytics_region,
            "domain_name": self.config.network.domain,
            "control_plane_location": self.config.apigee.control_plane_location,
            "billing_type": self.config.apigee.billing_type, 
            "apigee_billing_type": self.config.apigee.billing_type,
        }
        
        if self.config.apigee.consumer_data_region:
            tfvars_content["consumer_data_region"] = self.config.apigee.consumer_data_region
        
        tfvars_path = target_dir / "_apim_gen.auto.tfvars.json"
        with open(tfvars_path, "w") as f:
            json.dump(tfvars_content, f, indent=2)

    def _inject_configs(self, target_dir: Path, config_files: list[str]):
        """Resolves and copies explicit config files."""
        for i, path_str in enumerate(config_files):
            src = self.resolve_config_path(path_str)
            # Naming convention to ensure Load Order (later overrides earlier)
            dest_name = f"90_config_{i:02d}_{src.name}"
            if not dest_name.endswith(".auto.tfvars") and not dest_name.endswith(".opts"):
                 if src.suffix == ".tfvars":
                     dest_name = f"90_config_{i:02d}.auto.tfvars"
            
            shutil.copy2(src, target_dir / dest_name)
            console.print(f"[dim]  + Injected config: {src.name} -> {dest_name}[/dim]")

    def _copy_user_files(self, target_dir: Path):
        """
        Copies user's overlay *.tf and *.tfvars files to target_dir.
        STRICT POLICY: Only standard Terraform variables files are copied.
        apigee.tfvars is explicitly excluded/ignored.
        """
        reserved_prefixes = ["_apim_"]
        phase_name = target_dir.name
        
        # 1. Copy Config Files (*.tfvars) - Shared across all phases
        # Explicit allowlist of standard Terraform var files
        allowed_vars = ["terraform.tfvars", "*.auto.tfvars", "*.auto.tfvars.json"]
        
        for pattern in allowed_vars:
             for source_file in self.project_root.glob(pattern):
                shutil.copy2(source_file, target_dir / source_file.name)

        # 2. Copy Code Files (*.tf) - Phase 1 ONLY
        if phase_name == "1-main":
            for source_file in self.project_root.glob("*.tf"):
                if any(source_file.name.startswith(p) for p in reserved_prefixes):
                    continue
                shutil.copy2(source_file, target_dir / source_file.name)
