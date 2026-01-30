from scripts.cli.core import load_settings, save_settings

def cmd_config(args):
    """Manage global CLI settings."""
    settings = load_settings()
    
    if args.action == "set":
        settings[args.key] = args.value
        save_settings(settings)
        print(f"Set {args.key} = {args.value}")
    elif args.action == "get":
        if args.key:
            print(settings.get(args.key, "Not set"))
        else:
            for k, v in settings.items():
                print(f"{k} = {v}")
    elif args.action == "list":
        for k, v in settings.items():
            print(f"{k} = {v}")
