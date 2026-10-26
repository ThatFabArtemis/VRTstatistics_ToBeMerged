"""
Simple sanity-check script.

Plots CPU, memory, and bandwidth from a two-machine SimpleAvatar session.
Run from your experiment directory (the one containing run-* subdirectories):

    python simple-sanity-check.py [run-YYYYMMDD-HHMM]

If no run directory is given, the most recent run-* directory is used.
"""
import sys
import os
import glob

from VRTstatistics.datastore import DataStore
from VRTstatistics.plots import plot_resources
import matplotlib.pyplot as plt

if len(sys.argv) > 1:
    run_dir = sys.argv[1]
else:
    candidates = sorted(glob.glob("run-*"))
    if not candidates:
        print("No run-* directories found. Run VRTstatistics-ingest first.", file=sys.stderr)
        sys.exit(1)
    run_dir = candidates[-1]

combined_json = os.path.join(run_dir, "combined.json")
print(f"Using: {combined_json}")

ds = DataStore(combined_json)
ds.load()
plot_resources(ds)
plt.show()
