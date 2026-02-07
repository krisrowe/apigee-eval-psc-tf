# Standard packaging entry point for apim
from .commands.list import cmd_list
from .commands.show import cmd_show
from .commands.import_ import cmd_import
from .commands.terraform import run_terraform
from .commands.config import cmd_config
from .commands.apis import cmd_apis
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Apigee Terraform Multi-Env Utility")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("list")
    
    show = subparsers.add_parser("show")
    show.add_argument("name")
    show.add_argument("--raw", action="store_true")

    imp = subparsers.add_parser("import")
    imp.add_argument("name")
    imp.add_argument("--project")
    imp.add_argument("--force", action="store_true")
    imp.add_argument("--template")

    conf = subparsers.add_parser("config")
    conf_sub = conf.add_subparsers(dest="action", required=True)
    setter = conf_sub.add_parser("set")
    setter.add_argument("key")
    setter.add_argument("value")
    getter = conf_sub.add_parser("get")
    getter.add_argument("key", nargs="?")
    conf_sub.add_parser("show")
    conf_sub.add_parser("reset")

    apis = subparsers.add_parser("apis")
    apis_sub = apis.add_subparsers(dest="action", required=True)
    list_p = apis_sub.add_parser("list")
    list_p.add_argument("name")
    import_p = apis_sub.add_parser("import")
    import_p.add_argument("name")
    import_p.add_argument("--proxy-name", required=True)
    import_p.add_argument("--bundle", required=True)
    deploy_p = apis_sub.add_parser("deploy")
    deploy_p.add_argument("name")
    deploy_p.add_argument("--proxy-name", required=True)
    deploy_p.add_argument("--revision", required=True)
    deploy_p.add_argument("--environment", default="dev")
    test_p = apis_sub.add_parser("test")
    test_p.add_argument("name")
    test_p.add_argument("--proxy-name", required=True)
    test_p.add_argument("--bundle", required=True)
    test_p.add_argument("--environment", default="dev")

    for action in ["plan", "apply", "destroy", "refresh", "output", "init"]:
        p = subparsers.add_parser(action)
        p.add_argument("name")
        p.add_argument("extra_args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    if args.command == "list": cmd_list(args)
    elif args.command == "show": cmd_show(args)
    elif args.command == "import": cmd_import(args)
    elif args.command == "config": cmd_config(args)
    elif args.command == "apis": cmd_apis(args)
    elif args.command in ["plan", "apply", "destroy", "refresh", "output", "init"]:
        run_terraform(args.command, args.name, args.extra_args)
    else: parser.print_help()

if __name__ == "__main__":
    main()
