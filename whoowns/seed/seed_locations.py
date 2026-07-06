"""Normalize the cached city licensing records and upsert Locations.

Idempotent: keyed on (property_id, name), so re-running against a fresh pull
updates existing rows instead of duplicating them. Every seeded location is
linked to a Source row for the city dataset — nothing enters the DB without
provenance (spec §6).
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from whoowns.db import SessionLocal, init_db
from whoowns.models import Location, Source
from whoowns.neighborhoods import neighborhood_for_zip

# Boston City Hall; coordinates outside a loose box around the metro are
# geocoding errors in the source data and are treated as missing.
LAT_RANGE = (42.2, 42.5)
LNG_RANGE = (-71.3, -70.9)


def _clean_name(record: dict) -> str:
    raw = (record.get("dbaname") or "").strip() or (record.get("businessname") or "").strip()
    return raw.title() if raw.isupper() else raw


def _parse_coord(value, valid_range) -> float | None:
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if not (valid_range[0] <= coord <= valid_range[1]):
        return None
    return coord


def _address(record: dict) -> str:
    parts = [record.get("address"), record.get("city"), record.get("state"), record.get("zip")]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def seed_from_file(raw_path: Path) -> dict:
    """Load a cached pull and upsert locations. Returns summary counts."""
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    retrieved_at = datetime.fromisoformat(payload["retrieved_at"])
    records = [r for r in payload["records"] if (r.get("licstatus") or "").strip() == "Active"]

    init_db()
    session = SessionLocal()
    counts = {"inserted": 0, "updated": 0, "skipped_no_name": 0, "no_coords": 0}
    try:
        dataset_source = session.scalars(
            select(Source).where(Source.url == payload["dataset_page"])
        ).first()
        if dataset_source is None:
            dataset_source = Source(
                url=payload["dataset_page"],
                publisher="City of Boston / Analyze Boston",
                title="Active Food Establishment Licenses",
            )
            session.add(dataset_source)
        dataset_source.retrieved_at = retrieved_at

        existing = {
            (loc.property_id, loc.name): loc
            for loc in session.scalars(select(Location)).all()
        }

        for record in records:
            name = _clean_name(record)
            if not name:
                counts["skipped_no_name"] += 1
                continue
            lat = _parse_coord(record.get("latitude"), LAT_RANGE)
            lng = _parse_coord(record.get("longitude"), LNG_RANGE)
            if lat is None or lng is None:
                counts["no_coords"] += 1
                lat = lng = None
            property_id = (record.get("property_id") or "").strip() or None

            loc = existing.get((property_id, name))
            if loc is None:
                loc = Location(name=name, property_id=property_id)
                session.add(loc)
                existing[(property_id, name)] = loc
                counts["inserted"] += 1
            else:
                counts["updated"] += 1
            loc.address = _address(record)
            loc.lat = lat
            loc.lng = lng
            loc.neighborhood = neighborhood_for_zip(record.get("zip"))
            loc.license_category = (record.get("descript") or "").strip() or None
            if dataset_source not in loc.sources:
                loc.sources.append(dataset_source)

        session.commit()
    finally:
        session.close()
    return counts
