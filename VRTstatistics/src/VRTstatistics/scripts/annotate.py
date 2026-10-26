import sys
import os
import argparse
import re
from importlib.metadata import version as _pkg_version
from typing import Dict, List, Tuple, Any

from ..datastore import DataStore
from ..annotation import engine
from ._modimport import import_external_module


def _parse_annotation_arg(arg: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parse an annotation argument of the form 'name' or 'name(key=value,key=value)'.

    Returns (name, params_dict).
    """
    m = re.fullmatch(r'(\w+)(?:\(([^)]*)\))?', arg.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"Invalid annotation spec: {arg!r}. Expected 'name' or 'name(key=value,...)'")
    name = m.group(1)
    params: Dict[str, Any] = {}
    if m.group(2):
        for pair in m.group(2).split(","):
            pair = pair.strip()
            if not pair:
                continue
            k, _, v = pair.partition("=")
            params[k.strip()] = v.strip()
    return name, params


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply annotations to a combined.json DataStore produced by VRTstatistics-ingest"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version('VRTstatistics')}")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available annotation steps with their parameters and exit.",
    )
    parser.add_argument(
        "-a", "--annotate",
        metavar="NAME[(...)]",
        action="append",
        dest="annotations",
        default=[],
        help="Annotation to apply. Repeat for multiple. Use 'name(key=value,...)' to pass parameters.",
    )
    parser.add_argument(
        "--module",
        metavar="MODULE",
        action="append",
        dest="modules",
        default=[],
        help="Import MODULE before running (allows external steps to register themselves). If MODULE isn't importable as-is, searches upward from the current directory for a matching MODULE.py or MODULE/ package.",
    )
    parser.add_argument(
        "--pausefordebug",
        action="store_true",
        help="Wait for a newline after start (so you can attach a debugger)",
    )
    parser.add_argument(
        "--debugpy",
        action="store_true",
        help="Pause at begin of run to allow debugpy to attach",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="combined.json",
        help="DataStore file(s) to annotate",
    )
    args = parser.parse_args()

    if args.debugpy:
        import debugpy
        debugpy.listen(5678)
        print(f"{sys.argv[0]}: waiting for debugpy attach on 5678", flush=True)
        debugpy.wait_for_client()
        print(f"{sys.argv[0]}: debugger attached")
    if args.pausefordebug:
        sys.stderr.write(f"Attach debugger to pid={os.getpid()}. Press return to continue - ")
        sys.stderr.flush()
        sys.stdin.readline()

    for mod_name in args.modules:
        import_external_module(mod_name)

    if args.list:
        print(engine.list_steps())
        sys.exit(0)

    if not args.annotations:
        parser.error("At least one -a/--annotate argument is required")
    if not args.files:
        parser.error("At least one combined.json file is required")

    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for ann_arg in args.annotations:
        try:
            name, params = _parse_annotation_arg(ann_arg)
        except argparse.ArgumentTypeError as e:
            parser.error(str(e))
        parsed.append((name, params))

    ok = True
    for filepath in args.files:
        ds = DataStore(filepath)
        ds.load()
        for name, params in parsed:
            try:
                engine.ensure(ds, name, **params)
            except Exception as e:
                print(f"{filepath}: error applying annotation '{name}': {e}", file=sys.stderr)
                ok = False
                break
        else:
            ds.save()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
