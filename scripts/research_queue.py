"""Export the grey-area list: multi-site brands without confirmed ownership.

Usage: python scripts/research_queue.py

Writes data/research_queue.csv sorted by footprint — the manual research
to-do list, and later the input for the AI research pipeline (milestone 4).
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from whoowns.db import SessionLocal
from whoowns.engine import distinct_sites
from whoowns.models import Assessment, AssessmentStatus, Brand, SubjectType

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "research_queue.csv"


def main() -> None:
    with SessionLocal() as session:
        confirmed_ids = set(
            session.scalars(
                select(Assessment.subject_id).where(
                    Assessment.subject_type == SubjectType.brand,
                    Assessment.status != AssessmentStatus.estimated,
                )
            )
        )
        brands = session.scalars(
            select(Brand).options(joinedload(Brand.locations))
        ).unique().all()
        queue = sorted(
            (b for b in brands if b.id not in confirmed_ids and distinct_sites(b) >= 2),
            key=lambda b: -distinct_sites(b),
        )
        with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["brand_name", "distinct_sites", "licenses", "sample_address"])
            for b in queue:
                writer.writerow(
                    [b.name, distinct_sites(b), len(b.locations), b.locations[0].address]
                )
    print(f"{len(queue)} brands to research -> {OUT_PATH}")
    for b in queue[:10]:
        print(f"  {distinct_sites(b):3d} sites  {b.name}")


if __name__ == "__main__":
    main()
