import importlib
import os
import sys


def import_external_module(name: str) -> None:
    """
    Import a module by name, for its side effect of registering annotation
    steps/Views with the shared engine/registries.

    Tries a normal import first (so anything already on sys.path -- installed
    packages, etc. -- resolves exactly as importlib.import_module would).
    If that fails, searches upward from the current directory for a matching
    ``<name>.py`` file or ``<name>/__init__.py`` package, so a helper module
    that lives at the root of a per-experiment repo (not installed, not on
    sys.path) can still be found when running from a subdirectory (e.g. a
    session directory several levels below the repo root).
    """
    try:
        importlib.import_module(name)
        return
    except ModuleNotFoundError:
        pass

    directory = os.getcwd()
    while True:
        if os.path.isfile(os.path.join(directory, f"{name}.py")) or \
                os.path.isfile(os.path.join(directory, name, "__init__.py")):
            sys.path.insert(0, directory)
            importlib.import_module(name)
            return
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent

    raise ModuleNotFoundError(
        f"No module named {name!r} (not on sys.path, and no {name}.py or {name}/ package "
        f"found in {os.getcwd()} or any parent directory)"
    )
