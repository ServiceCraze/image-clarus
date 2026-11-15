import argparse
import sys
from importlib.metadata import version


class VersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(f"image-clarus {version('image-clarus')}")
        parser.exit()


def main():
    parser = argparse.ArgumentParser(prog="image-clarus")
    parser.add_argument("--version", action=VersionAction, nargs=0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    process = subparsers.add_parser(
        "process",
        help="Process one image",
        description="Outputs are create-only by default; search is a help-only stub.",
    )
    process.add_argument("IMAGE")
    process.add_argument("--config", metavar="FILE")
    process.add_argument("--stages", metavar="STAGES", help="Default: desc,json")
    process.add_argument("--set", metavar="PATH=VALUE", action="append")
    for option in ("--desc-prompt", "--json-prompt", "--json-schema"):
        process.add_argument(option, metavar="FILE")
    process.add_argument("--regenerate", action="store_true")
    process.add_argument(
        "--missing-prerequisite", choices=("fail", "skip"), help="Default: fail"
    )
    subparsers.add_parser("search", help="Search (not implemented in Slice 1)")
    args = parser.parse_args()
    if args.command == "search":
        print("search is not implemented in Slice 1", file=sys.stderr)
    else:
        print("process is not implemented yet", file=sys.stderr)
    return 3
