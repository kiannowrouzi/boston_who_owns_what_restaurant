"""Fetch the Active Food Establishment Licenses dataset from Analyze Boston.

Pages through the CKAN datastore API and caches the raw records plus a
retrieval timestamp to data/raw/. No API key required; dataset refreshes
daily.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CKAN_API = "https://data.boston.gov/api/3/action/datastore_search"
RESOURCE_ID = "f1e13724-284d-478c-b8bc-ef042aa5b70b"
DATASET_PAGE = (
    "https://data.boston.gov/dataset/active-food-establishment-licenses"
)
PAGE_SIZE = 1000

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"


def fetch_all(timeout: int = 60) -> dict:
    """Return {"retrieved_at": iso8601, "records": [...]} for the full dataset."""
    records = []
    offset = 0
    while True:
        resp = requests.get(
            CKAN_API,
            params={"resource_id": RESOURCE_ID, "limit": PAGE_SIZE, "offset": offset},
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        page = result["records"]
        records.extend(page)
        offset += len(page)
        if not page or offset >= result["total"]:
            break
    return {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "dataset_page": DATASET_PAGE,
        "resource_id": RESOURCE_ID,
        "records": records,
    }


def fetch_and_cache() -> Path:
    """Fetch the dataset and write it to data/raw/, returning the file path."""
    payload = fetch_all()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["retrieved_at"][:10]
    out_path = RAW_DIR / f"active_food_licenses_{stamp}.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"Fetched {len(payload['records'])} records -> {out_path}")
    return out_path
