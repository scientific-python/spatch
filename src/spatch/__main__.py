import argparse

from .backend_utils import update_entrypoint, verify_entrypoint


def main():
    parser = argparse.ArgumentParser(prog="python -m spatch")
    subparsers = parser.add_subparsers(help="subcommand help", required=True, dest="subcommand")

    update_entrypoint_cmd = subparsers.add_parser(
        "update-entrypoints", help="update the entrypoint toml file"
    )
    update_entrypoint_cmd.add_argument(
        "paths", type=str, nargs="+", help="paths to the entrypoint toml files to update"
    )
    update_entrypoint_cmd.add_argument(
        "--verify",
        action="store_true",
        help="verify updated entrypoints",
    )

    verify_entrypoint_cmd = subparsers.add_parser(
        "verify-entrypoints", help="verify the entrypoint toml file"
    )
    verify_entrypoint_cmd.add_argument(
        "paths", type=str, nargs="+", help="paths to the entrypoint toml files to verify"
    )
    verify_entrypoint_cmd.add_argument(
        "--optional-module",
        action="append",
        type=str,
        help="add a top-level module that may be ignored during verification "
        "(useful when identifiers refer to optional packages)",
    )

    args = parser.parse_args()
    verify = False
    optional_modules = None
    if args.subcommand == "update-entrypoints":
        for path in args.paths:
            update_entrypoint(path)
        verify = args.verify
    elif args.subcommand == "verify-entrypoints":
        verify = True
        if args.optional_module:
            optional_modules = set(args.optional_module)
    else:
        raise RuntimeError("unreachable: subcommand not known.")
    if verify:
        for path in args.paths:
            verify_entrypoint(path, optional_modules=optional_modules)


if __name__ == "__main__":
    main()
