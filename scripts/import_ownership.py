"""Import human-verified ownership claims from data/ownership_curated.csv.

Usage: python scripts/import_ownership.py

Only rows with verified=y become Confirmed — verify means YOU opened the
source URL and it supports the claim. Run scripts/assess.py afterwards so
estimates skip the newly confirmed brands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whoowns.ownership_import import CURATED_PATH, import_curated


def main() -> None:
    counts = import_curated()
    print(f"Confirmed {counts['confirmed']} brand(s).")
    if counts["unverified_skipped"]:
        print(
            f"{counts['unverified_skipped']} row(s) skipped — not verified. Open each "
            f"source_url in {CURATED_PATH}, confirm it supports the claim, set "
            f"verified=y, and re-run."
        )
    for name in counts["brand_not_found"]:
        print(f"WARNING: no brand named '{name}' in the DB — check spelling against the app.")


if __name__ == "__main__":
    main()
