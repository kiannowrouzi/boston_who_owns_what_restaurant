"""Who Owns Your Restaurant? — Boston v1 (Streamlit, milestone 2).

Search + map + detail over the seeded location list. Every location currently
shows the honest "not yet assessed" state (spec: unknown is a first-class
state, not a failure).
"""

import pandas as pd
import pydeck as pdk
import streamlit as st
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from whoowns.db import SessionLocal, init_db
from whoowns.models import Assessment, AssessmentStatus, Location, SubjectType

# Pin colors: categorical hues (violet/aqua) for confirmed statuses and an
# ordered one-hue blue ramp for the likelihood buckets — deliberately not
# red/green, which would editorialize; ownership is an identity, not a defect.
# Violet vs. dark blue can converge under CVD, so confirmed pins also carry a
# size encoding, and tooltips state the status in text.
STATUS_STYLE = {
    "Confirmed investor-backed": {"color": [74, 58, 167, 230], "radius": 7},
    "Confirmed independent": {"color": [27, 175, 122, 230], "radius": 7},
    "Likely": {"color": [16, 66, 129, 200], "radius": 4},
    "Possible": {"color": [42, 120, 214, 185], "radius": 4},
    "Unlikely": {"color": [134, 182, 239, 170], "radius": 3},
    "Not assessed": {"color": [137, 135, 129, 150], "radius": 3},
}
STATUS_BUCKETS = list(STATUS_STYLE)
PIN_OUTLINE = [252, 252, 251, 200]

BOSTON_CENTER = (42.3251, -71.0789)
FUZZY_CUTOFF = 60


def _bucket(assessment: Assessment | None) -> str:
    if assessment is None:
        return "Not assessed"
    if assessment.status == AssessmentStatus.confirmed_pe:
        return "Confirmed investor-backed"
    if assessment.status == AssessmentStatus.confirmed_independent:
        return "Confirmed independent"
    return assessment.label if assessment.label in STATUS_STYLE else "Not assessed"


def _latest_brand_assessments(session) -> dict[int, Assessment]:
    result: dict[int, Assessment] = {}
    for a in session.scalars(
        select(Assessment)
        .where(Assessment.subject_type == SubjectType.brand)
        .order_by(Assessment.computed_at)
    ):
        result[a.subject_id] = a
    return result


@st.cache_data(ttl=300)
def load_locations() -> pd.DataFrame:
    init_db()
    with SessionLocal() as session:
        assessments = _latest_brand_assessments(session)
        rows = session.scalars(
            select(Location).options(joinedload(Location.brand))
        ).all()
        return pd.DataFrame(
            [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "address": loc.address,
                    "lat": loc.lat,
                    "lng": loc.lng,
                    "neighborhood": loc.neighborhood or "Unknown",
                    "license_category": loc.license_category or "Unknown",
                    "brand": loc.brand.name if loc.brand else None,
                    "brand_locations": loc.brand.location_count if loc.brand else 1,
                    "status": _bucket(
                        assessments.get(loc.brand_id) if loc.brand_id else None
                    ),
                    "updated_at": loc.updated_at,
                }
                for loc in rows
            ]
        )


def fuzzy_filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    matches = process.extract(
        query,
        df["name"],
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_CUTOFF,
        limit=50,
    )
    if not matches:
        return df.iloc[0:0]
    index_order = [idx for _, _, idx in matches]
    return df.loc[index_order]


def render_map(df: pd.DataFrame) -> None:
    mappable = df.dropna(subset=["lat", "lng"]).copy()
    mappable["color"] = mappable["status"].map(lambda s: STATUS_STYLE[s]["color"])
    confirmed_mask = mappable["status"].str.startswith("Confirmed")
    columns = ["name", "address", "status", "lat", "lng", "color"]

    def pin_layer(rows: pd.DataFrame, min_px: int, max_px: int) -> pdk.Layer:
        return pdk.Layer(
            "ScatterplotLayer",
            data=rows[columns].to_dict("records"),
            get_position="[lng, lat]",
            get_fill_color="color",
            get_radius=30,
            radius_min_pixels=min_px,
            radius_max_pixels=max_px,
            get_line_color=PIN_OUTLINE,
            line_width_min_pixels=1,
            stroked=True,
            pickable=True,
        )

    st.pydeck_chart(
        pdk.Deck(
            initial_view_state=pdk.ViewState(
                latitude=BOSTON_CENTER[0], longitude=BOSTON_CENTER[1], zoom=11
            ),
            layers=[
                pin_layer(mappable[~confirmed_mask], 3, 10),
                pin_layer(mappable[confirmed_mask], 6, 14),
            ],
            tooltip={"text": "{name}\n{address}\n{status}"},
        )
    )
    legend = "&nbsp;&nbsp;".join(
        f'<span style="color:rgb({s["color"][0]},{s["color"][1]},{s["color"][2]})">●</span>'
        f' <span style="color:#52514e">{name}</span>'
        for name, s in STATUS_STYLE.items()
    )
    st.markdown(legend, unsafe_allow_html=True)
    off_map = len(df) - len(mappable)
    if off_map:
        st.caption(f"{off_map} matching spot(s) lack usable coordinates and appear only in the list.")


def render_detail(location_id: int) -> None:
    with SessionLocal() as session:
        loc = session.get(Location, location_id)
        st.subheader(loc.name)
        st.write(loc.address or "No address on file")
        col1, col2 = st.columns(2)
        col1.metric("Neighborhood", loc.neighborhood or "Unknown")
        col2.metric("License category", loc.license_category or "Unknown")

        if loc.brand is not None:
            st.markdown("#### Brand")
            if loc.brand.location_count > 1:
                st.write(
                    f"Part of **{loc.brand.name}** — {loc.brand.location_count} "
                    f"Boston locations under this brand. Ownership research "
                    f"happens at the brand level, so an assessment here will "
                    f"cover all of them."
                )
                siblings = [s for s in loc.brand.locations if s.id != loc.id]
                with st.expander(f"Other {loc.brand.name} locations"):
                    for sib in sorted(siblings, key=lambda s: s.address or ""):
                        st.write(f"- {sib.name} — {sib.address or 'no address'}")
            else:
                st.write(f"Single-location brand: **{loc.brand.name}**.")

        st.markdown("#### Ownership assessment")
        assessment = (
            _latest_brand_assessments(session).get(loc.brand_id)
            if loc.brand_id
            else None
        )
        if assessment is None:
            st.info(
                "**Estimated — not yet assessed.** No ownership research has been "
                "run for this location. When it has, you'll see either a documented, "
                "sourced ownership chain or a likelihood range with the reasoning "
                "behind it."
            )
        elif assessment.status != AssessmentStatus.estimated:
            backed = assessment.status == AssessmentStatus.confirmed_pe
            st.markdown(
                f"**Confirmed {'investor-backed' if backed else 'independent'}** "
                f"(documented ownership, human-verified sources)."
            )
            parent = loc.brand.parent
            if parent is not None:
                chain = f"{loc.brand.name} → **{parent.name}** ({parent.type.value.replace('_', ' ')})"
                for inv in parent.investors:
                    chain += f" → **{inv.name}** ({inv.type.value.replace('_', ' ')})"
                st.markdown(chain)
                if parent.notes:
                    st.caption(parent.notes)
            if assessment.evidence:
                for src in assessment.evidence:
                    verified = (
                        f" — verified {src.verified_at:%Y-%m-%d}" if src.verified_at else ""
                    )
                    st.markdown(f"- [{src.title or src.url}]({src.url}) ({src.publisher}){verified}")
        else:
            st.markdown(
                f"**{assessment.label}** — estimated "
                f"{assessment.likelihood_low:.0f}–{assessment.likelihood_high:.0f}% "
                f"likelihood of outside-investor backing. This is an estimate from "
                f"public signals, not a documented fact."
            )
            for reason in assessment.reasoning or []:
                st.markdown(f"- {reason}")
            st.caption(
                f"Model {assessment.model_version}, computed "
                f"{assessment.computed_at:%Y-%m-%d}."
            )

        st.markdown("#### Sources")
        if loc.sources:
            for src in loc.sources:
                retrieved = (
                    f" — retrieved {src.retrieved_at:%Y-%m-%d}" if src.retrieved_at else ""
                )
                st.markdown(f"- [{src.title or src.url}]({src.url}) ({src.publisher}){retrieved}")
        else:
            st.write("No sources recorded.")
        st.caption(f"Record last updated {loc.updated_at:%Y-%m-%d}.")


def main() -> None:
    st.set_page_config(page_title="Who Owns Your Restaurant? — Boston", layout="wide")
    st.title("Who Owns Your Restaurant? — Boston")
    st.caption(
        "A directory of Boston food establishments and what's known about who owns "
        "them. Ownership assessments are estimates unless documented and human-verified; "
        "every claim will show its sources."
    )

    df = load_locations()
    if df.empty:
        st.warning("No data yet — run `python scripts/seed.py` first.")
        return

    with st.sidebar:
        st.header("Find a restaurant")
        query = st.text_input("Search by name", placeholder="e.g. Neponset Cafe")
        neighborhoods = st.multiselect(
            "Neighborhood", sorted(df["neighborhood"].unique())
        )
        categories = st.multiselect(
            "License category", sorted(df["license_category"].unique())
        )
        statuses = st.multiselect("Ownership status", STATUS_BUCKETS)
        chains_only = st.checkbox("Multi-location brands only (2+)")

    filtered = df
    if neighborhoods:
        filtered = filtered[filtered["neighborhood"].isin(neighborhoods)]
    if categories:
        filtered = filtered[filtered["license_category"].isin(categories)]
    if statuses:
        filtered = filtered[filtered["status"].isin(statuses)]
    if chains_only:
        filtered = filtered[filtered["brand_locations"] >= 2]
    if query.strip():
        filtered = fuzzy_filter(filtered, query.strip())

    st.write(f"**{len(filtered)}** of {len(df)} establishments shown")
    render_map(filtered)

    if filtered.empty:
        st.write("No matches. Try loosening the search or filters.")
        return

    options = filtered.head(200)
    labels = {
        row.id: f"{row.name} — {row.address or 'no address'}" for row in options.itertuples()
    }
    selected = st.selectbox(
        "Select a restaurant for details",
        options=list(labels),
        format_func=labels.get,
    )
    if selected is not None:
        render_detail(selected)


main()
