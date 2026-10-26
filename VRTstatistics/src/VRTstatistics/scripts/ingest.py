import sys
import os
import argparse
from importlib.metadata import version as _pkg_version
from typing import List, Tuple

from ..datastore import DataStore
from ..normalizer import SessionNormalizer
from ..scripts.annotate import _parse_annotation_arg
from ..scripts._modimport import import_external_module
from ..annotation import engine
from VRTrun import Session, SessionConfig

verbose = True

def main():
    parser = argparse.ArgumentParser(description="Run a test, or ingest results")

    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version('VRTstatistics')}")
    parser.add_argument("-a", "--annotate", metavar="NAME[(...)]", action="append", dest="annotations", default=[], help="Annotation to apply after ingesting (same syntax as VRTstatistics-annotate). Repeat for multiple.")
    parser.add_argument("--module", metavar="MODULE", action="append", dest="modules", default=[], help="Import MODULE before annotating (allows external annotation steps to register themselves). If MODULE isn't importable as-is, searches upward from the current directory for a matching MODULE.py or MODULE/ package. Repeat for multiple.")
    parser.add_argument("--norun", metavar="DIR", help="Don't run the test, only ingest data from an earlier run)")
    parser.add_argument("--config", metavar="DIR", default="./config", help="Config directory to use (default: ./config)")
    parser.add_argument("--pausefordebug", action="store_true", help="Wait for a newline after start (so you can attach a debugger)")
    parser.add_argument("--debugpy", action="store_true", help="Pause at begin of run to allow debugpuy to attach")
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

    # Check that we have either a config or hosts
    configdir = args.config
    if not os.path.exists(configdir):
        print(f"{parser.prog}: Error: config directory {configdir} does not exist", file=sys.stderr)
        sys.exit(1)

    sessionconfig = SessionConfig.from_configdir(configdir)

    #
    # First we run the session (if needed)
    #
    if args.norun:
        workdir = args.norun
    else:

        workdir = Session.invent_workdir()

        session = Session(sessionconfig, configdir, workdir, verbose=verbose)

        session.start()

        session.run()

        sts = session.wait()

        session.receive_results()

        if sts != 0:
            print(f"{parser.prog}: Error: session failed with status {sts}", file=sys.stderr)
            return sts

    datastores : List[Tuple[str, DataStore]] = []
    for machine_role, _ in sessionconfig.get_machines():
        machine_stats_filename = os.path.join(workdir, machine_role, "stats.log")
        machine_rusage_filename = os.path.join(workdir, machine_role, "rusage.log")
        machine_vq_filename = os.path.join(workdir, machine_role, "vq-brisque.log" )
        if os.path.exists(machine_vq_filename):
            print(f"{parser.prog}: Using visual quality data from {machine_vq_filename}")
            extra_filename = machine_vq_filename
        elif os.path.exists(machine_rusage_filename):
            extra_filename = machine_rusage_filename
        else:
            print(f"{parser.prog}: Warning: no rusage data found at {machine_rusage_filename}")
            extra_filename = None
        machine_data = DataStore(machine_stats_filename,extra_filename )
        machine_data.load()
        datastores.append((machine_role, machine_data))
   
    combined_filename = os.path.join(workdir, "combined.json")

    outputdata = DataStore(combined_filename)
    normalizer = SessionNormalizer(datastores, outputdata)
    ok = normalizer.normalize()

    for ann_arg in args.annotations:
        try:
            name, params = _parse_annotation_arg(ann_arg)
            engine.ensure(outputdata, name, **params)
        except Exception as e:
            print(f"{parser.prog}: Error applying annotation '{ann_arg}': {e}", file=sys.stderr)
            ok = False

    outputdata.save()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
