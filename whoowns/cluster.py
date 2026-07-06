"""Brand clustering (spec §4 step 2, milestone 3).

Groups locations into brands in three passes:
1. Name normalization — exact match on the cleaned name.
2. Fuzzy matching over unique normalized names — pairs scoring >= AUTO_MERGE
   are merged automatically; pairs in the review band are written to
   data/brand_review.csv for a human decision.
3. Human decisions — fill the `same_brand` column in brand_review.csv with
   y/n and re-run; `y` forces a merge, `n` blocks one (including would-be
   auto-merges). Undecided pairs stay separate (conservative default) and
   remain in the file.

The spec calls for an LLM sanity-check on ambiguous pairs; until an API key
is configured, the review CSV is that check, done by hand.

Idempotent: brands are recomputed each run, upserted by display name, and
orphaned brands are deleted.
"""

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from whoowns.db import SessionLocal, init_db
from whoowns.models import Brand, Location

AUTO_MERGE = 94
REVIEW_MIN = 87
# Fuzzy scores on very short names are noise ("cafe one" vs "cafe zone").
MIN_FUZZY_LEN = 6

REVIEW_PATH = Path(__file__).resolve().parent.parent / "data" / "brand_review.csv"
REVIEW_FIELDS = ["name_a", "name_b", "score", "locations_a", "locations_b", "same_brand"]

_PAREN = re.compile(r"\(.*?\)")
_STORE_NUM = re.compile(r"#\s*\d+")
_APOSTROPHE = re.compile(r"['’.]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_CORP_SUFFIX = re.compile(r"\b(llc|inc|incorporated|corp|corporation|ltd|company)\b")


def normalize_name(name: str) -> str:
    n = name.lower()
    n = _PAREN.sub(" ", n)
    n = _STORE_NUM.sub(" ", n)
    n = n.replace("&", " and ")
    n = _APOSTROPHE.sub("", n)
    n = _NON_ALNUM.sub(" ", n)
    n = _CORP_SUFFIX.sub(" ", n)
    n = n.strip()
    if n.startswith("the "):
        n = n[4:]
    return " ".join(n.split())


class _UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _load_review() -> dict[tuple[str, str], dict]:
    if not REVIEW_PATH.exists():
        return {}
    with REVIEW_PATH.open(newline="", encoding="utf-8") as f:
        return {_pair_key(row["name_a"], row["name_b"]): row for row in csv.DictReader(f)}


def _write_review(rows: dict[tuple[str, str], dict]) -> None:
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for key in sorted(rows, key=lambda k: -float(rows[k].get("score") or 0)):
            writer.writerow({field: rows[key].get(field, "") for field in REVIEW_FIELDS})


def cluster_brands() -> dict:
    """Recompute brand clusters and assignments. Returns summary counts."""
    init_db()
    session = SessionLocal()
    try:
        locations = session.scalars(select(Location)).all()
        by_norm: dict[str, list[Location]] = defaultdict(list)
        for loc in locations:
            by_norm[normalize_name(loc.name)].append(loc)
        by_norm.pop("", None)

        names = sorted(by_norm)
        uf = _UnionFind(names)
        review = _load_review()
        decided = {
            key: row["same_brand"].strip().lower()
            for key, row in review.items()
            if row.get("same_brand", "").strip()
        }

        # Fuzzy pass over unique normalized names.
        fuzzable = [n for n in names if len(n) >= MIN_FUZZY_LEN]
        scores = process.cdist(
            fuzzable, fuzzable, scorer=fuzz.token_sort_ratio,
            score_cutoff=REVIEW_MIN, workers=-1,
        )
        review_band = 0
        for i in range(len(fuzzable)):
            for j in range(i + 1, len(fuzzable)):
                score = scores[i][j]
                if score < REVIEW_MIN:
                    continue
                key = _pair_key(fuzzable[i], fuzzable[j])
                decision = decided.get(key)
                if decision in ("y", "yes"):
                    uf.union(*key)
                elif decision in ("n", "no"):
                    continue
                elif score >= AUTO_MERGE:
                    uf.union(*key)
                else:
                    review_band += 1
                    if key not in review:
                        review[key] = {
                            "name_a": key[0],
                            "name_b": key[1],
                            "score": f"{score:.0f}",
                            "locations_a": str(len(by_norm[key[0]])),
                            "locations_b": str(len(by_norm[key[1]])),
                            "same_brand": "",
                        }

        # Human-forced merges may involve names outside the fuzzy band.
        for key, decision in decided.items():
            if decision in ("y", "yes") and key[0] in uf.parent and key[1] in uf.parent:
                uf.union(*key)

        _write_review(review)

        clusters: dict[str, list[Location]] = defaultdict(list)
        for norm, locs in by_norm.items():
            clusters[uf.find(norm)].extend(locs)

        existing = {b.name: b for b in session.scalars(select(Brand)).all()}
        for locs in clusters.values():
            display = Counter(loc.name for loc in locs).most_common(1)[0][0]
            brand = existing.get(display)
            if brand is None:
                brand = Brand(name=display)
                session.add(brand)
                existing[display] = brand
            brand.location_count = len(locs)
            for loc in locs:
                loc.brand = brand
        session.flush()

        orphans = [
            b for b in session.scalars(
                select(Brand).options(joinedload(Brand.locations))
            ).unique()
            if not b.locations
        ]
        for brand in orphans:
            session.delete(brand)
        session.commit()

        multi = [locs for locs in clusters.values() if len(locs) > 1]
        return {
            "locations": len(locations),
            "brands": len(clusters),
            "multi_location_brands": len(multi),
            "largest": max((len(l) for l in clusters.values()), default=0),
            "pending_review": sum(
                1 for row in review.values() if not row.get("same_brand", "").strip()
            ),
            "orphan_brands_removed": len(orphans),
        }
    finally:
        session.close()
