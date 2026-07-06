"""Rule-based likelihood engine v1 (spec §3, milestone 5).

Produces an estimated Assessment per brand from signals available in the
licensing data alone. v1 has one primary signal — distinct physical sites —
because it is the strongest per the spec and the only one we can compute
without external data. Distinct *sites*, not licenses: one venue can hold
many licenses (stadium stands), and expansion is what the signal means.

Confirmed assessments bypass the engine entirely; brands that have one are
skipped. Estimates are ranges with reasoning, never bare numbers.

Known blind spot, stated in every small-footprint estimate: counts are
Boston-only, so a national chain with one Boston outpost scores Unlikely
until its ownership is documented via the curated import.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from whoowns.db import SessionLocal, init_db
from whoowns.models import Assessment, AssessmentStatus, Brand, SubjectType

MODEL_VERSION = "rules-v1"

BOSTON_ONLY_CAVEAT = (
    "Counts reflect City of Boston licenses only — a small local footprint "
    "does not rule out a larger chain elsewhere."
)


def distinct_sites(brand: Brand) -> int:
    sites = {loc.property_id or loc.address or f"loc-{loc.id}" for loc in brand.locations}
    return len(sites)


def score_brand(brand: Brand) -> dict:
    """Map a brand's footprint to a labeled likelihood range with reasoning."""
    sites = distinct_sites(brand)
    licenses = len(brand.locations)
    reasoning = []
    if licenses != sites:
        reasoning.append(
            f"{licenses} licenses across {sites} physical site(s) — multiple "
            f"licenses at one venue don't indicate expansion."
        )

    if sites <= 1:
        label, low, high = "Unlikely", 10, 30
        reasoning.append(
            "Single Boston site with no expansion footprint — the profile of "
            "an independent operator."
        )
        reasoning.append(BOSTON_ONLY_CAVEAT)
    elif sites <= 4:
        label, low, high = "Possible", 40, 60
        reasoning.append(
            f"{sites} Boston sites — a small multi-location footprint; equally "
            f"consistent with a family-run local group or an early rollup."
        )
        reasoning.append(BOSTON_ONLY_CAVEAT)
    elif sites <= 9:
        label, low, high = "Likely", 70, 85
        reasoning.append(
            f"{sites} Boston sites — a footprint this size usually requires "
            f"outside capital or a restaurant group behind it."
        )
    else:
        label, low, high = "Likely", 75, 90
        reasoning.append(
            f"{sites} Boston sites — chain-scale presence in a single metro."
        )

    reasoning.append("No documented ownership on file — this is an estimate.")
    return {"label": label, "low": low, "high": high, "reasoning": reasoning}


def assess_all() -> dict:
    """Re-run the engine over every brand without a confirmed assessment."""
    init_db()
    session = SessionLocal()
    try:
        brands = session.scalars(
            select(Brand).options(joinedload(Brand.locations))
        ).unique().all()
        confirmed_ids = set(
            session.scalars(
                select(Assessment.subject_id).where(
                    Assessment.subject_type == SubjectType.brand,
                    Assessment.status != AssessmentStatus.estimated,
                )
            )
        )

        session.execute(
            delete(Assessment).where(
                Assessment.subject_type == SubjectType.brand,
                Assessment.status == AssessmentStatus.estimated,
            )
        )

        counts = {"Unlikely": 0, "Possible": 0, "Likely": 0, "skipped_confirmed": 0}
        for brand in brands:
            if brand.id in confirmed_ids:
                counts["skipped_confirmed"] += 1
                continue
            verdict = score_brand(brand)
            session.add(
                Assessment(
                    subject_id=brand.id,
                    subject_type=SubjectType.brand,
                    status=AssessmentStatus.estimated,
                    likelihood_low=verdict["low"],
                    likelihood_high=verdict["high"],
                    label=verdict["label"],
                    reasoning=verdict["reasoning"],
                    model_version=MODEL_VERSION,
                )
            )
            counts[verdict["label"]] += 1
        session.commit()
        return counts
    finally:
        session.close()
