"""Config command implementation using the config SDK."""

from scripts.cli.config_sdk import get_config_manager, CliConfig
from dataclasses import fields


def cmd_config(args):
    """Manage global CLI settings using strongly-typed SDK."""
    config_mgr = get_config_manager()
    
    if args.action == "set":
        key = args.key
        
        # Validate that key exists in CliConfig
        valid_keys = {f.name for f in fields(CliConfig)}
        if key not in valid_keys:
            print(f"ERROR: Unknown setting '{key}'")
            print(f"\nValid settings:")
            for field in fields(CliConfig):
                print(f"  {field.name}")
            return
        
        config_mgr.set(key, args.value)
        print(f"Set {key} = {args.value}")
        
    elif args.action == "get":
        if args.key:
            # Get specific key
            valid_keys = {f.name for f in fields(CliConfig)}
            if args.key not in valid_keys:
                print(f"ERROR: Unknown setting '{args.key}'")
                return
            
            value = config_mgr.get(args.key)
            print(f"{args.key} = {value if value is not None else '(not set)'}")
        else:
            # Show all settings
            config = config_mgr.load()
            print("Current settings:")
            for field in fields(CliConfig):
                value = getattr(config, field.name)
                status = value if value is not None else '(not set)'
                print(f"  {field.name} = {status}")
                
    elif args.action == "show":
        # Show all settings with descriptions
        print("Available settings:\n")
        config = config_mgr.load()
        
        # Manually document each setting (could be enhanced with field metadata)
        settings_docs = {
            'default_root_domain': {
                'description': 'Default root domain for auto-generated hostnames',
                'example': 'example.com'
            }
        }
        
        for field in fields(CliConfig):
            value = getattr(config, field.name)
            status = value if value is not None else '(not set)'
            doc = settings_docs.get(field.name, {'description': 'No description', 'example': 'N/A'})
            
            print(f"{field.name}:")
            print(f"  Description: {doc['description']}")
            print(f"  Current: {status}")
            print(f"  Example: {doc['example']}")
            print()
            
    elif args.action == "reset":
        # Clear all settings
        config_mgr.reset()
        print("All settings cleared")
