"""Cluster locations into brands (milestone 3).

Usage: python scripts/cluster.py

Re-run after editing data/brand_review.csv (fill same_brand with y/n) to
apply your decisions. Safe to re-run any time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whoowns.cluster import REVIEW_PATH, cluster_brands


def main() -> None:
    counts = cluster_brands()
    print(
        f"Clustered {counts['locations']} locations into {counts['brands']} brands "
        f"({counts['multi_location_brands']} with 2+ locations; largest has "
        f"{counts['largest']})."
    )
    if counts["orphan_brands_removed"]:
        print(f"Removed {counts['orphan_brands_removed']} orphaned brand(s).")
    if counts["pending_review"]:
        print(
            f"{counts['pending_review']} ambiguous pair(s) await review: fill the "
            f"same_brand column (y/n) in {REVIEW_PATH} and re-run."
        )


if __name__ == "__main__":
    main()
