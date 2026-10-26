"""
Latency analysis script.

Plots per-component latency contributions and end-to-end latency,
frame rates, and point counts from a two-machine latency experiment.
Run from your experiment directory (the one containing run-* subdirectories):

    python latency-analysis.py [run-YYYYMMDD-HHMM]

If no run directory is given, the most recent run-* directory is used.
"""
import sys
import os
import glob

from VRTstatistics.datastore import DataStore
from VRTstatistics.plots import plot_latencies, plot_framerates_and_dropped, plot_pointcounts
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

plot_latencies(ds)
plt.figure()
plot_framerates_and_dropped(ds)
plt.figure()
plot_pointcounts(ds)
plt.show()
