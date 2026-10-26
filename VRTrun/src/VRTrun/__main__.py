import sys
import os
import argparse
from importlib.metadata import version as _pkg_version
from . import Session, SessionConfig

def main():
    parser = argparse.ArgumentParser(description="Run a VR2Gather player session")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version('VRTrun')}")
    parser.add_argument("--config", metavar="DIR", default="./config", help="Config directory to use (default: ./config)")
    parser.add_argument("--host", action="append", metavar="HOST", help="Don't use config but simply run on HOST. May be repeated")
    parser.add_argument("--quiet", action="store_true", dest="quiet", help="Don't print progress messages")
    parser.add_argument("--pausefordebug", action="store_true", help="Pause before starting to allow attaching a debugger")
    # xxxjack add machines
    
    args = parser.parse_args()
    verbose = not args.quiet
    if args.pausefordebug:
        sys.stderr.write(f"Attach debugger to pid={os.getpid()}. Press return to continue - ")
        sys.stderr.flush()
        sys.stdin.readline()
    # Check that we have either a config or hosts
    sessionconfig : SessionConfig
    if args.host:
        if os.path.exists(args.config):
            print(f"{parser.prog}: Error: don't use --host if a config directory exists", file=sys.stderr)
            sys.exit(1)
        configdir = None
        sessionconfig = SessionConfig.from_hostlist(args.host)
    else:
        if not os.path.exists(args.config):
            print(f"{parser.prog}: Error: config directory {args.config} does not exist", file=sys.stderr)
            sys.exit(1)
        configdir = args.config
        sessionconfig = SessionConfig.from_configdir(configdir)

    workdir = Session.invent_workdir()

    session = Session(sessionconfig, configdir, workdir, verbose=verbose)

    session.start()

    session.run()

    sts = session.wait()

    session.receive_results()

    return sts

if __name__ == "__main__":
    main()
