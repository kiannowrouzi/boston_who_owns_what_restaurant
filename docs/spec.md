# Technical & Requirements Spec — "Who Owns Your Restaurant?" (Boston v1)

**Version:** 0.1 (draft)
**Scope:** Single metro (Boston) proof-of-concept
**One-line description:** A searchable, mapped directory that estimates whether a Boston restaurant is private-equity / outside-investor backed, showing confirmed ownership where documented and a transparent, sourced likelihood estimate where not.

---

## 1. Product goals & non-goals

### Goals
- Let a user look up a Boston restaurant and see an ownership assessment: **Confirmed PE/investor-backed**, **Confirmed independent**, or an **estimated likelihood** when undocumented.
- Every confirmed claim links to a source. Every estimate shows the reasoning behind it.
- Be honest about uncertainty: "unknown/estimated" is a first-class state, not a failure.
- Be maintainable by one person a few hours a week.

### Non-goals (v1)
- National coverage. One metro only.
- Certifying every independent spot. The value is flagging the *backed* ones; most pins stay estimated.
- Real-time deal tracking. Weekly/monthly refresh is fine.
- User accounts, social features, reviews.

---

## 2. Core concepts / data model

The heart of the app is an ownership graph. Four main entities:

**Location** — a physical storefront.
`id, name, address, lat, lng, neighborhood, cuisine, price_tier, brand_id (nullable), source_ids[], created_at, updated_at`

**Brand** — the concept/chain a location belongs to (a single independent spot is a brand with one location).
`id, name, location_count, founded_year, website, parent_id (nullable), group_id (nullable)`

**Parent / Owner** — the corporate entity or restaurant group that owns the brand.
`id, name, type (independent | restaurant_group | private_equity | strategic | public_co | unknown), notes`

**PE_Firm / Investor** — the fund or investor, when ownership is investor-backed.
`id, name, type (pe | vc | growth_equity | family_office | strategic), website`

**Assessment** — the computed ownership verdict for a location or brand.
`id, subject_id, subject_type (location|brand), status (confirmed_pe | confirmed_independent | estimated), likelihood_low, likelihood_high, label (Confirmed|Likely|Possible|Unlikely), reasoning[], evidence_ids[], model_version, computed_at`

**Source / Evidence** — every claim's provenance.
`id, url, publisher, title, excerpt, retrieved_at, verified_by_human (bool), verified_at`

Key design points:
- Ownership is layered: a location → brand → parent → investor chain. "PE-owned" can be true at the brand level while the specific franchised location is independently operated — model that, and surface it in the UI copy.
- **Confirmed** statuses require at least one `Source` with `verified_by_human = true`. No human verification, no "Confirmed."
- **Estimated** assessments store the ranged likelihood and the list of reasons, never a bare number.

---

## 3. The likelihood engine (v1: transparent rules, not ML)

For v1, use a **rule-based additive score**, not a trained classifier — you won't have enough clean labels for a defensible model, and rules are explainable, which is a legal/trust necessity here.

Each signal contributes weighted points; the total maps to a labeled range. Every contributing signal is stored in `reasoning[]` and shown to the user.

Suggested starting signals (tune weights against your seed data):

| Signal | Direction | Rough weight |
|---|---|---|
| Location count (1 → many) | more locations → higher | strongest |
| Rapid recent expansion | higher | strong |
| Member of known restaurant group | higher | strong |
| Unified branding / careers page / gift-card infra | higher | moderate |
| Fast-casual format | higher | moderate |
| Shared registered agent / LLC network in state filings | higher | moderate |
| Single location, no expansion, family-run signals | lower | strong |

Output mapping (illustrative):
- `Confirmed` — documented, bypasses the score entirely (100% / 0%).
- `Likely` — e.g. 70–90% range
- `Possible` — e.g. 40–70%
- `Unlikely` — e.g. 10–40%

**Display as ranges with reasoning, never a sharp two-decimal number.** A "73%" reads as a fact; a "70–85%, because: 6 locations, rapid expansion, unified branding" reads as an estimate, which is what it is. Store `model_version` so scores are reproducible when you retune.

---

## 4. Data pipeline

**Seeding (one-time-ish):**
1. Pull the establishment list from City of Boston open food-inspection data + Google/Yelp Places for enrichment (lat/lng, cuisine, price).
2. Cluster locations into brands (name normalization + fuzzy match + LLM sanity-check on ambiguous pairs).
3. For each brand, run AI-assisted research (LLM + web search) to find documented ownership — returns candidate parent/investor + source URLs.
4. **Human verification gate:** you review each proposed confirmed claim; clicking through the source is mandatory before it's marked `verified_by_human`.
5. For brands with no documented ownership, run the rule engine to produce an estimated assessment.

**Maintenance (recurring, mostly passive):**
- Scheduled job monitors local food press (Eater Boston, Globe, Boston Mag) for acquisition/investment keywords, flags matches to your review queue.
- Re-run the rule engine when signals change (e.g., a brand opens new locations).

**Hard rule:** no AI-sourced ownership claim is published as "Confirmed" without a human checking the source says what the model claims. AI drafts; you approve.

---

## 5. Functional requirements

- **Search** — fuzzy search by restaurant name; typo-tolerant.
- **Map view** — pins across Boston, colored by status (confirmed PE / confirmed independent / estimated buckets).
- **Filters** — by status/likelihood bucket, neighborhood, cuisine, investor.
- **Detail page** — for a location/brand: the assessment, the ownership chain (location → brand → parent → investor), every source link, and for estimates the full reasoning list.
- **Correction/appeal path** — a visible "this is wrong / I own this" submission form. Non-optional; your false positives (successful independents that look like rollups) will generate these.
- **"Unknown" is honest** — spots with no data show as estimated with low confidence, clearly labeled, never as a confident verdict.

## 6. Non-functional requirements

- **Sourcing/transparency:** every confirmed claim cites a source; every estimate shows reasoning. This is a product requirement, not a nicety — it's your defamation buffer.
- **Reproducibility:** assessments store `model_version` and `computed_at`.
- **Freshness:** data staleness visible (show `updated_at`).
- **Legal:** don't ingest/redistribute paywalled databases' proprietary data (PitchBook/Mergr terms). Use them for your own research leads only, cite the primary source. Include a disclaimer that estimates are estimates.

---

## 7. Tech stack & hosting

### Stage 1 — Streamlit (recommended start)
**Use it to:** validate the concept, do your seeding, demo to testers.
- App: Streamlit (search box, `st.map` / `pydeck` for the map, filters, detail views).
- Data: SQLite or a hosted Postgres (Supabase free tier) — put the data in a real DB from day one so it survives the eventual migration.
- Research pipeline: standalone Python scripts (LLM + web search) writing into the same DB, run separately from the app.
- Hosting: Streamlit Community Cloud (free) or a small container.

**Adequate because** the audience is small, you need speed-to-first-version, and Streamlit gives you map + search + filters with almost no frontend work.

**Its limits (why it's Stage 1, not forever):**
- No clean per-restaurant URLs — poor SEO. A public "who owns X restaurant" directory *lives or dies on search discovery*, and this is the real reason to migrate.
- Server-rendered; cost/performance degrades with concurrent public traffic.
- Limited layout/polish control.

### Stage 2 — "real website" (migrate if it gets traction)
- Frontend/app: **Next.js** (per-restaurant indexable pages for SEO, better UX/perf).
- Search: Typesense or Algolia for fuzzy search.
- DB: **Postgres** (Supabase/Neon) — unchanged from Stage 1.
- Maps: Mapbox / Google Maps.
- Hosting: Vercel (app) + managed Postgres.
- Pipeline: same Python research scripts, now as scheduled jobs.

**The migration is cheap** because only the presentation layer changes. Your data model (§2), likelihood engine (§3), and pipeline (§4) are stack-agnostic and carry over intact. That's the whole reason to not over-invest in Stage 1's frontend.

### Decision rule
Start on Streamlit. Migrate to Next.js when *either*: (a) you want the public to find restaurants via Google search, or (b) concurrent usage makes the Streamlit model creak. Until then, Streamlit is the right, faster choice.

---

## 8. Suggested build order (milestones)

1. **DB + schema** (§2) in Postgres. Even for the Streamlit version.
2. **Seed Boston locations** from open data; basic Streamlit map + search over raw list.
3. **Brand clustering** + manual cleanup.
4. **AI research pipeline** → review queue → confirmed assessments with sources.
5. **Rule-based likelihood engine** for the unconfirmed remainder.
6. **Detail pages + reasoning display + correction form.**
7. Ship to a handful of testers. Iterate weights against reality.
8. *(If traction)* Rebuild frontend on Next.js for SEO/scale; port pipeline to scheduled jobs.

---

## 9. Known risks (carry these forward)

- **False positives on beloved independents** that grew organically to several locations — they look identical to a PE rollup to any feature set. Correction path + "estimated, here's why" framing are the mitigations.
- **Defamation exposure** — bare numbers read as accusations. Always show sources/reasoning; keep humans in the confirm loop.
- **Staleness** — PE flips on a 5–7yr cycle. Surface `updated_at`; keep the press-monitoring job running.
- **The undocumented majority** — most independent spots will forever be "estimated." Design around that honestly rather than faking omniscience.
