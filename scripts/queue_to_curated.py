"""Append unconfirmed brands in a size band to data/ownership_curated.csv.

Usage: python scripts/queue_to_curated.py [--min 4] [--max 19]

Adds one blank row per brand (license count within the band, not already in
the file) with helper columns (licenses, sites, sample_address) for research
context. Fill in owner/source columns, set verified=y after checking the
source, then run scripts/import_ownership.py. The import ignores the helper
columns.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from whoowns.db import SessionLocal
from whoowns.engine import distinct_sites
from whoowns.models import Brand
from whoowns.ownership_import import CURATED_PATH

FIELDS = [
    "brand_name", "owner_name", "owner_type", "investor_name", "investor_type",
    "source_url", "source_title", "source_publisher", "verified", "notes",
    "licenses", "sites", "sample_address",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=int, default=4)
    parser.add_argument("--max", type=int, default=19)
    args = parser.parse_args()

    with CURATED_PATH.open(newline="", encoding="utf-8-sig") as f:
        existing = list(csv.DictReader(f))
    known = {row["brand_name"].strip() for row in existing}

    with SessionLocal() as session:
        brands = session.scalars(
            select(Brand)
            .where(Brand.location_count >= args.min, Brand.location_count <= args.max)
            .options(joinedload(Brand.locations))
            .order_by(Brand.location_count.desc())
        ).unique().all()
        added = []
        for b in brands:
            if b.name in known:
                continue
            added.append(
                {
                    "brand_name": b.name,
                    "licenses": len(b.locations),
                    "sites": distinct_sites(b),
                    "sample_address": b.locations[0].address if b.locations else "",
                }
            )

    with CURATED_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in existing + added:
            writer.writerow({field: row.get(field, "") for field in FIELDS})

    print(f"Added {len(added)} brand(s) to {CURATED_PATH} ({len(existing)} already present).")
    for row in added:
        print(f"  {row['licenses']:3d} lic / {row['sites']:2d} sites  {row['brand_name']}")


if __name__ == "__main__":
    main()
