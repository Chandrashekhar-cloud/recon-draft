"""Script to copy saved v2 reconciliation results into cache/ for offline replay."""

import json
from pathlib import Path
import shutil

BASE_DIR = Path(__file__).resolve().parent
RESULTS_V2_DIR = BASE_DIR / "results" / "v2"
CACHE_DIR = BASE_DIR / "cache"


def cache_saved_runs() -> None:
    """Copy all available v2 results into cache/ for instant offline replay."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not RESULTS_V2_DIR.is_dir():
        print(f"Error: results/v2 directory not found at {RESULTS_V2_DIR}")
        return

    copied_count = 0
    for v2_file in sorted(RESULTS_V2_DIR.glob("*.json")):
        dst_file = CACHE_DIR / v2_file.name
        shutil.copy2(v2_file, dst_file)
        copied_count += 1
        print(f"Cached: {v2_file.name} -> cache/{dst_file.name}")

    print(f"\nSuccessfully cached {copied_count} v2 run results into {CACHE_DIR}.")


if __name__ == "__main__":
    cache_saved_runs()
