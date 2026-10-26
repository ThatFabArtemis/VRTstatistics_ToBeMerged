import argparse
import sys
import os
from importlib.metadata import version as _pkg_version

from ..datastore import DataStore


def main():
    parser = argparse.ArgumentParser(description="Export selected fields from a datastore to CSV")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version('VRTstatistics')}")
    parser.add_argument("-d", "--datastore", required=True, help="datastore file to export from")
    parser.add_argument(
        "-o", "--output", metavar="FILE", required=True, help="Output CSV file"
    )
    parser.add_argument(
        "-p",
        "--predicate",
        metavar="EXPR",
        default=None,
        help="If specified export only data that matches EXPR predicate"
    )
    parser.add_argument(
        "fields", default=None, nargs="*", metavar="FIELD", help="Field mappings to export (default: all)"
    )
    parser.add_argument("--pausefordebug", action="store_true", help="Wait for a newline after start (so you can attach a debugger)")
    args = parser.parse_args()
    if args.pausefordebug:
        sys.stderr.write(f"Attach debugger to pid={os.getpid()}. Press return to continue - ")
        sys.stderr.flush()
        sys.stdin.readline()

    datastore = DataStore(args.datastore)
    datastore.load()

    fields = args.fields if args.fields else None
    df = datastore.get_dataframe(args.predicate, fields)
    df.to_csv(args.output, index=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
