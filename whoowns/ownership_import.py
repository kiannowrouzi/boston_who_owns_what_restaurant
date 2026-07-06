"""Import human-verified ownership claims from data/ownership_curated.csv.

The verification gate (spec §4, hard rule): a row becomes a Confirmed
assessment ONLY if its `verified` column is `y` — meaning a human opened
`source_url` and checked it supports the claim. Unverified rows are reported
and skipped, never published.

CSV columns:
  brand_name    exact Brand.name in the DB
  owner_name    the parent entity (company, group, or fund)
  owner_type    independent | restaurant_group | private_equity | strategic | public_co
  investor_name optional backing investor (e.g. the PE fund behind a platform)
  investor_type pe | vc | growth_equity | family_office | strategic
  source_url    where the claim is documented
  source_title, source_publisher
  verified      y = human checked the source; anything else = skipped
  notes         surfaced in the UI (e.g. "locations are franchisee-operated")

Idempotent: re-running updates existing parents/investors/sources by name/url
and replaces the brand's assessments.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from whoowns.db import SessionLocal, init_db
from whoowns.models import (
    Assessment,
    AssessmentStatus,
    Brand,
    Investor,
    InvestorType,
    Parent,
    ParentType,
    Source,
    SubjectType,
)

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "ownership_curated.csv"

# Investor-backed vs independent: public and PE/strategic-owned brands are
# "outside capital"; independents and self-owned local groups are not.
BACKED_OWNER_TYPES = {ParentType.private_equity, ParentType.public_co, ParentType.strategic}

# Curation vocabulary is free-form; map it onto the schema's types. The
# curator's original wording stays visible via the notes column.
OWNER_TYPE_ALIASES = {
    "founder_owned": ParentType.independent,
    "family_owned": ParentType.independent,
    "franchise_brand": ParentType.restaurant_group,
    "local_chain": ParentType.restaurant_group,
    "venue_concessionaire": ParentType.restaurant_group,
    "hotel_management": ParentType.restaurant_group,
    "university_auxiliary": ParentType.restaurant_group,
    "vc_backed": ParentType.restaurant_group,
    "private_co": ParentType.strategic,
}
INVESTOR_TYPE_ALIASES = {
    "investment_holding": InvestorType.family_office,
    "restaurant_investor": InvestorType.strategic,
    "public_co": InvestorType.strategic,
    "real_estate_investor": InvestorType.strategic,
    "franchise_development_partner": InvestorType.strategic,
}


def _parent_type(raw: str) -> ParentType:
    raw = raw.strip().lower()
    return OWNER_TYPE_ALIASES.get(raw) or ParentType(raw)


def _investor_type(raw: str) -> InvestorType:
    raw = raw.strip().lower()
    return INVESTOR_TYPE_ALIASES.get(raw) or InvestorType(raw)


def _read_curated() -> list[dict]:
    # Excel commonly re-saves the file as cp1252; fall back if UTF-8 fails.
    try:
        with CURATED_PATH.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except UnicodeDecodeError:
        with CURATED_PATH.open(newline="", encoding="cp1252") as f:
            return list(csv.DictReader(f))


def import_curated() -> dict:
    init_db()
    session = SessionLocal()
    counts = {"confirmed": 0, "unverified_skipped": 0, "brand_not_found": []}
    now = datetime.now(timezone.utc)
    try:
        rows = _read_curated()

        parents = {p.name: p for p in session.scalars(select(Parent)).all()}
        investors = {i.name: i for i in session.scalars(select(Investor)).all()}
        sources = {s.url: s for s in session.scalars(select(Source)).all()}
        seen_parents: set[str] = set()

        for row in rows:
            brand_name = row["brand_name"].strip()
            if row.get("verified", "").strip().lower() not in ("y", "yes"):
                counts["unverified_skipped"] += 1
                continue
            brand = session.scalars(select(Brand).where(Brand.name == brand_name)).first()
            if brand is None:
                counts["brand_not_found"].append(brand_name)
                continue

            owner_name = row["owner_name"].strip()
            owner_type = _parent_type(row["owner_type"])
            parent = parents.get(owner_name)
            if parent is None:
                parent = Parent(name=owner_name)
                session.add(parent)
                parents[owner_name] = parent
            parent.type = owner_type
            parent.notes = row.get("notes", "").strip() or None
            brand.parent = parent
            if owner_name not in seen_parents:
                # First row for this parent this run: rebuild its investor links.
                parent.investors.clear()
                seen_parents.add(owner_name)

            investor_name = row.get("investor_name", "").strip()
            investor_names = [
                n.strip() for n in investor_name.split(";")
                if n.strip() and n.strip() != owner_name
            ]
            for name in investor_names:
                investor = investors.get(name)
                if investor is None:
                    investor = Investor(name=name, type=_investor_type(row["investor_type"]))
                    session.add(investor)
                    investors[name] = investor
                if investor not in parent.investors:
                    parent.investors.append(investor)

            url = row["source_url"].strip()
            source = sources.get(url)
            if source is None:
                source = Source(url=url)
                session.add(source)
                sources[url] = source
            source.title = row.get("source_title", "").strip() or None
            source.publisher = row.get("source_publisher", "").strip() or None
            source.verified_by_human = True
            source.verified_at = now

            backed = bool(investor_name) or owner_type in BACKED_OWNER_TYPES
            status = AssessmentStatus.confirmed_pe if backed else AssessmentStatus.confirmed_independent
            chain = f"{brand.name} → {owner_name}"
            if investor_name:
                chain += f" → {investor_name}"

            session.flush()
            session.execute(
                delete(Assessment).where(
                    Assessment.subject_type == SubjectType.brand,
                    Assessment.subject_id == brand.id,
                )
            )
            assessment = Assessment(
                subject_id=brand.id,
                subject_type=SubjectType.brand,
                status=status,
                likelihood_low=100 if backed else 0,
                likelihood_high=100 if backed else 0,
                label="Confirmed",
                reasoning=[f"Documented ownership: {chain}."],
                model_version="curated-v1",
            )
            assessment.evidence.append(source)
            session.add(assessment)
            counts["confirmed"] += 1

        session.commit()
        return counts
    finally:
        session.close()
