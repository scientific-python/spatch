import argparse

from .backend_utils import update_entrypoint


def main():
    parser = argparse.ArgumentParser(prog="python -m spatch")
    subparsers = parser.add_subparsers(help="subcommand help", required=True, dest="subcommand")

    update_entrypoint_cmd = subparsers.add_parser(
        "update-entrypoints", help="update the entrypoint toml file"
    )
    update_entrypoint_cmd.add_argument(
        "paths", type=str, nargs="+", help="paths to the entrypoint toml files to update"
    )

    args = parser.parse_args()

    if args.subcommand == "update-entrypoints":
        for path in args.paths:
            update_entrypoint(path)
    else:
        raise RuntimeError("unreachable: subcommand not known.")


if __name__ == "__main__":
    main()
