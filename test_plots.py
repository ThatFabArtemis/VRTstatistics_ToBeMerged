#!/usr/bin/env python3
"""
Regression test for plot output. For each run directory passed as argument:
  - Renames existing plots to .old. variants
  - Regenerates all applicable plots using the current API
  - Does NOT show plots interactively; saves to files for eyeball comparison

Usage:
  python test_plots.py <run-dir> [<run-dir> ...]

All plot types are attempted. Plots requiring nTiles > 1 are skipped silently
for single-tile runs.
"""
import sys
import os
import shutil
import traceback

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as pyplot

from VRTstatistics.datastore import DataStore, DataStoreError
import VRTstatistics.plots as plots


PLOTARGS = dict(alpha=0.6)


def rename_old(dir: str, name: str) -> None:
    """Rename dir/name to dir/<stem>.old.<ext> if it exists."""
    src = os.path.join(dir, name)
    stem, ext = os.path.splitext(name)   # "latency", ".png"
    dst = os.path.join(dir, f"{stem}.old{ext}")
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  saved old → {os.path.basename(dst)}")


def try_plot(label: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        print(f"  {label}: OK")
        return result
    except Exception as e:
        print(f"  {label}: FAILED — {e}")
        traceback.print_exc()
        return None
    finally:
        pyplot.close('all')


def process_dir(run_dir: str) -> None:
    print(f"\n=== {run_dir}")
    combined = os.path.join(run_dir, "combined.json")
    if not os.path.exists(combined):
        print("  SKIP: no combined.json")
        return

    ds = DataStore(combined)
    ds.load()

    nTiles = ds.applied_annotations.get("latency", {}).get("nTiles", 1)
    print(f"  nTiles={nTiles}")

    # Rename existing plots to .old before regenerating
    for name in ["latency.png", "framerates.pdf", "resources.pdf",
                 "pointcounts.pdf", "progress.pdf", "latencies-per-tile.pdf"]:
        rename_old(run_dir, name)

    # latency
    try_plot("plot_latencies", plots.plot_latencies,
        ds,
        showplot=False, saveplot=True,
        dirname=run_dir, file_name="latency.png",
        dpi=150, format="png",
        ncols=2, use_row_major=False, labelspacing=0.2,
        figsize=(6.4, 3.5),
        title="Latency contributions",
        show_disruptions=True,
        plotargs=PLOTARGS,
    )

    # framerates
    try_plot("plot_framerates_and_dropped", plots.plot_framerates_and_dropped,
        ds,
        showplot=False, saveplot=True,
        dirname=run_dir,
        plotargs=PLOTARGS,
    )

    # resources
    try_plot("plot_resources", plots.plot_resources,
        ds,
        showplot=False, saveplot=True,
        dirname=run_dir,
    )

    # pointcounts
    try_plot("plot_pointcounts", plots.plot_pointcounts,
        ds,
        showplot=False, saveplot=True,
        dirname=run_dir,
    )

    # progress
    try_plot("plot_progress", plots.plot_progress,
        ds,
        showplot=False, saveplot=True,
        dirname=run_dir,
    )

    # latencies per tile (only if nTiles > 1)
    if nTiles > 1:
        try_plot("plot_latencies_per_tile", plots.plot_latencies_per_tile,
            ds,
            showplot=False, saveplot=True,
            dirname=run_dir,
        )
    else:
        print("  plot_latencies_per_tile: SKIP (nTiles=1)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for run_dir in sys.argv[1:]:
        process_dir(os.path.abspath(run_dir))
    print("\nDone.")


if __name__ == "__main__":
    main()
