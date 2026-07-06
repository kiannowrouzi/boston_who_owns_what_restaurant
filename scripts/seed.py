"""Fetch the Boston licensing data and seed the database, end to end.

Usage: python scripts/seed.py [--from-cache path/to/raw.json]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whoowns.seed.fetch_boston import fetch_and_cache
from whoowns.seed.seed_locations import seed_from_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-cache",
        type=Path,
        help="Seed from an existing raw JSON pull instead of fetching",
    )
    args = parser.parse_args()

    raw_path = args.from_cache if args.from_cache else fetch_and_cache()
    counts = seed_from_file(raw_path)
    print(
        f"Seed complete: {counts['inserted']} inserted, {counts['updated']} updated, "
        f"{counts['no_coords']} without map coordinates, "
        f"{counts['skipped_no_name']} skipped (no name)."
    )


if __name__ == "__main__":
    main()
