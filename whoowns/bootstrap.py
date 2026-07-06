"""One-shot pipeline bootstrap for empty databases (e.g. fresh cloud deploys).

Streamlit Community Cloud starts with no database — data/app.db is gitignored,
so a deployed app has empty tables until this runs. It rebuilds the DB from
scratch: fetch open data, seed, cluster, import verified ownership, score
estimates. The curated inputs it depends on (ownership_curated.csv,
brand_review.csv) ARE committed, so the whole pipeline runs on the cloud.

Cheap to check (a COUNT), so it's safe to call on every startup; it only does
work when the Location table is empty. On Community Cloud the filesystem is
ephemeral, so this re-runs (~30-60s) after each cold start.
"""

from collections.abc import Callable

from sqlalchemy import func, select

from whoowns.db import SessionLocal, init_db
from whoowns.models import Location

# Ordered pipeline steps; each is (label, thunk). Imports are deferred so a
# warm start (DB already populated) doesn't pay for them.
def _steps() -> list[tuple[str, Callable]]:
    from whoowns.cluster import cluster_brands
    from whoowns.engine import assess_all
    from whoowns.ownership_import import import_curated
    from whoowns.seed.fetch_boston import fetch_and_cache
    from whoowns.seed.seed_locations import seed_from_file

    state: dict = {}

    def fetch():
        state["raw"] = fetch_and_cache()

    def seed():
        seed_from_file(state["raw"])

    return [
        ("Fetching Boston food-license data", fetch),
        ("Seeding locations", seed),
        ("Clustering brands", cluster_brands),
        ("Importing verified ownership", import_curated),
        ("Scoring likelihood estimates", assess_all),
    ]


def database_is_empty() -> bool:
    init_db()
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Location)) == 0


def bootstrap_if_empty(on_step: Callable[[str], None] | None = None) -> bool:
    """Build the DB from scratch if it has no locations. Returns True if it ran."""
    if not database_is_empty():
        return False
    for label, thunk in _steps():
        if on_step is not None:
            on_step(label)
        thunk()
    return True
