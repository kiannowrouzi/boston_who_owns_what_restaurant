# Who Owns Your Restaurant? — Boston v1

A searchable, mapped directory that estimates whether a Boston restaurant is
private-equity / outside-investor backed — confirmed ownership where documented
(always with sources), and a transparent, reasoned likelihood estimate where not.

Full requirements: [docs/spec.md](docs/spec.md). This repo currently implements
**milestones 1–3 and 5**: the full ownership-graph schema, a seed pipeline from
City of Boston open data, brand clustering with a human-review loop, a rule-based
likelihood engine, a human-verified confirmed-ownership import, and a Streamlit
app (fuzzy search, status-colored map, filters, assessment detail views). The AI
research pipeline (milestone 4) is the remaining piece and needs an Anthropic
API key.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Seed the database

Pulls ~3,300 active food establishment licenses from
[Analyze Boston](https://data.boston.gov/dataset/active-food-establishment-licenses)
(public CKAN API, no key needed) and upserts them into a local SQLite DB at
`data/app.db`. Idempotent — re-run any time for fresh data.

```powershell
python scripts\seed.py
```

Set `DATABASE_URL` to point at Postgres (e.g. Supabase) instead of SQLite; the
schema is written to run on both unchanged.

## Cluster locations into brands

Groups the seeded locations into brands (chains become one brand with many
locations). Confident name matches merge automatically; ambiguous pairs are
written to `data/brand_review.csv` — fill the `same_brand` column with `y`/`n`
and re-run to apply your decisions. Idempotent; run after each re-seed.

```powershell
python scripts\cluster.py
```

## Assess ownership

```powershell
python scripts\assess.py           # rule-based estimates for every unconfirmed brand
python scripts\import_ownership.py # publish human-verified confirmed ownership
python scripts\research_queue.py   # export the grey-area list to data\research_queue.csv
```

The confirm workflow: `data/ownership_curated.csv` holds proposed ownership rows
with source links. **Open each source URL, check it supports the claim, set
`verified=y`, then run the import** — unverified rows are never published
(spec's hard rule). Run `assess.py` again afterwards so estimates skip the
newly confirmed brands. Estimates use distinct physical sites (not license
counts) as the primary signal and always display as ranges with reasoning.

## Run the app

```powershell
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)

Point [share.streamlit.io](https://share.streamlit.io) at this repo, branch
`main`, main file `app.py`. The database is gitignored, so on first launch the
app **seeds itself** — fetching the open data, clustering, importing the
verified ownership, and scoring estimates (~30-60s, see
[whoowns/bootstrap.py](whoowns/bootstrap.py)). Community Cloud's filesystem is
ephemeral, so this re-runs after each cold start. For a persistent, faster
deployment, set a `DATABASE_URL` secret pointing at hosted Postgres (Supabase/
Neon) and seed it once with the scripts above.

## Layout

- `whoowns/models.py` — the ownership graph (spec §2): Location, Brand, Parent,
  Investor, Assessment, Source. All six entities exist now so later milestones
  need no migrations.
- `whoowns/seed/` — fetch + normalize + upsert pipeline (spec §4, step 1).
- `whoowns/cluster.py` — brand clustering with review loop (spec §4, step 2).
- `app.py` — Streamlit UI (spec §5 subset).
- `docs/spec.md` — the full requirements spec, including the likelihood engine
  design, data pipeline, and roadmap.
