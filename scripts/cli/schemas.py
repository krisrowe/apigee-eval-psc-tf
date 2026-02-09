import json
from dataclasses import dataclass, fields, field
from typing import Optional, List

class SchemaValidationError(Exception):
    pass

@dataclass
class ApigeeOrgConfig:
    """
    Core Apigee Configuration (Immutable-ish properties).
    Used for templates ('apim create') and status reporting.
    """
    # Core
    billing_type: str = "EVALUATION"
    drz: bool = False  # Feature Toggle
    
    # Regions
    analytics_region: Optional[str] = None       # Allowed only if drz=False
    runtime_location: Optional[str] = None       # Always required
    control_plane_location: Optional[str] = None # Allowed only if drz=True
    consumer_data_region: Optional[str] = None   # Allowed only if drz=True
    
    # Helper / Naming
    instance_name: Optional[str] = None
    
    # Validation Logic
    def validate(self):
        # 1. DRZ vs Standard Mutually Exclusive Check
        if self.drz:
            # DRZ Mode
            if self.analytics_region:
                raise SchemaValidationError("Configuration Error (DRZ=True): 'analytics_region' must NOT be set. Use 'consumer_data_region' instead.")
            if not self.control_plane_location:
                 raise SchemaValidationError("Configuration Error (DRZ=True): 'control_plane_location' is required.")
            if not self.consumer_data_region:
                raise SchemaValidationError("Configuration Error (DRZ=True): 'consumer_data_region' is required.")
            
            # Billing Check for DRZ
            if self.billing_type == "EVALUATION":
                raise SchemaValidationError("Configuration Error (DRZ=True): 'billing_type' cannot be 'EVALUATION'. DRZ requires PAYG or SUBSCRIPTION.")
        else:
            # Standard Mode
            if self.control_plane_location or self.consumer_data_region:
                raise SchemaValidationError("Configuration Error (DRZ=False): DRZ fields ('control_plane_location', 'consumer_data_region') are not allowed.")
            if not self.analytics_region:
                raise SchemaValidationError("Configuration Error (DRZ=False): 'analytics_region' is required.")
            
        # Common
        if not self.runtime_location:
            raise SchemaValidationError("Configuration Error: 'runtime_location' is required.")

    @classmethod
    def from_json_file(cls, path: str) -> 'ApigeeOrgConfig':
        with open(path, 'r') as f:
            data = json.load(f)
        
        # 1. Strict Key Check (No Unknown Fields)
        known = {f.name for f in fields(cls)}
        unknown = set(data.keys()) - known
        if unknown:
            raise SchemaValidationError(f"Unknown fields in input JSON: {unknown}. Allowed: {known}")
            
        # 2. Type/Field Loading
        try:
            instance = cls(**data)
        except TypeError as e:
            raise SchemaValidationError(f"Type Mismatch or Argument Error: {e}")
            
        # 3. Logical Validation
        instance.validate()
        
        return instance

    def to_tfvars(self, project_id: str) -> str:
        """Converts the schema to valid HCL tfvars content."""
        lines = [f'gcp_project_id = "{project_id}"']
        
        if self.billing_type:
             lines.append(f'apigee_billing_type = "{self.billing_type}"')
             
        if self.instance_name:
             lines.append(f'apigee_instance_name = "{self.instance_name}"')
             
        # Regions
        if self.analytics_region:
            lines.append(f'apigee_analytics_region = "{self.analytics_region}"')
            
        if self.runtime_location:
            lines.append(f'apigee_runtime_location = "{self.runtime_location}"')
            
        if self.control_plane_location:
            lines.append(f'control_plane_location = "{self.control_plane_location}"')
            
        if self.consumer_data_region:
            lines.append(f'consumer_data_region = "{self.consumer_data_region}"')

        return "\n".join(lines) + "\n"

# Alias for backward compatibility if needed, though we should update usages
ApigeeOrgTemplate = ApigeeOrgConfig

@dataclass
class ApigeeProjectStatus:
    """
    Operational Status View.
    Contains the immutable config plus live operational state.
    """
    project_id: str
    config: ApigeeOrgConfig
    
    # Operational State
    subscription_type: str = "-"  # From API (PAID/TRIAL) - distinct from billing_type config
    environments: List[str] = field(default_factory=list)
    instances: List[str] = field(default_factory=list)
    ssl_status: str = "-"
    
    @property
    def is_drz(self) -> bool:
        return self.config.drz

