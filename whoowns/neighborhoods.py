"""Static Boston ZIP → neighborhood mapping for v1 filters.

Coarse by design: some ZIPs span neighborhoods; the licensing data has no
neighborhood field, and this avoids a geocoding dependency (spec: no external
APIs in milestone 2). Unknown ZIPs map to None.
"""

ZIP_TO_NEIGHBORHOOD = {
    "02108": "Beacon Hill",
    "02109": "North End",
    "02110": "Downtown",
    "02111": "Chinatown",
    "02113": "North End",
    "02114": "West End",
    "02115": "Fenway",
    "02116": "Back Bay",
    "02118": "South End",
    "02119": "Roxbury",
    "02120": "Mission Hill",
    "02121": "Dorchester",
    "02122": "Dorchester",
    "02124": "Dorchester",
    "02125": "Dorchester",
    "02126": "Mattapan",
    "02127": "South Boston",
    "02128": "East Boston",
    "02129": "Charlestown",
    "02130": "Jamaica Plain",
    "02131": "Roslindale",
    "02132": "West Roxbury",
    "02134": "Allston",
    "02135": "Brighton",
    "02136": "Hyde Park",
    "02163": "Allston",
    "02199": "Back Bay",
    "02201": "Downtown",
    "02203": "Downtown",
    "02205": "Downtown",
    "02210": "Seaport",
    "02215": "Fenway",
    "02467": "Chestnut Hill",
}


def neighborhood_for_zip(zip_code: str | None) -> str | None:
    if not zip_code:
        return None
    return ZIP_TO_NEIGHBORHOOD.get(zip_code.strip()[:5].zfill(5))
