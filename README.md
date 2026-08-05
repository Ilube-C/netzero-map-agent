# SW England Renewable-Energy Projects — Map Agent

A conversational AI you talk to in a sidebar next to an interactive map. The
agent answers natural-language questions about renewable-energy projects across
South West England — *"operational solar over 10 MW"*, *"battery projects within
25 km of Exeter"*, *"break down the pipeline by county"* — by calling tools that
run either **client-side** (the map view) or **server-side** against **PostGIS**.

The data is the public **DESNZ Renewable Energy Planning Database (REPD)** — real
operators, capacities, development stages, and site coordinates. No private or
employer data is used anywhere in this project.

```
┌─────────── Browser ───────────┐         ┌────────── Backend (FastAPI) ─┐
│  Map (MapLibre GL JS)         │◄──WS───▶│  Agent loop (LLM tool-use)   │
│  Chat sidebar                 │  view   │   ├─ view tools  → browser   │
│  executes map commands        │  cmds   │   └─ data tools  → PostGIS   │
└───────────────────────────────┘         │  PostGIS (spatial queries)   │
                                          └──────────────────────────────┘
```

## Architecture in one idea

Tools live on **two execution surfaces**, and the LLM never touches Mapbox or
Postgres directly — it emits a structured tool call and a dispatcher routes it:

| Surface | Runs where | Tools |
|---|---|---|
| **View** | Browser (MapLibre/Mapbox GL JS) | `fly_to`, `set_layer_color`, `set_layer_visibility`, `clear_map` |
| **Data** | Server (PostGIS) | `search_projects`, `projects_within_distance`, `nearest_projects`, `area_summary`, `show_footprint`, `geocode_place` |

**The model never handles raw geometry.** Spatial tools take a *place name*
(`"Bath"`, `"Devon"`) and geocode it **server-side**; data tools render results
as map layers but return only a **compact text summary** (counts, MW, technology
and development-stage breakdown) to the model. Keeping coordinates out of the
model's context removes a weak model's main failure mode — copying / hallucinating
lat-longs between calls — and lets a small free model (Llama 3.3 70B on Groq)
drive the whole thing reliably. The provider is swappable in one place
(`backend/app/agent.py`): Groq, Gemini, Ollama, or Anthropic.

## Geospatial engineering

All spatial work is PostGIS, exercised through the agent:

- **`ST_Transform`** — REPD ships OSGB36 eastings/northings (EPSG:27700); they're
  reprojected to WGS84 (EPSG:4326) in-database when `db/init.sql` loads.
- **`ST_DWithin`** (geography) — radius search ("within 25 km of Exeter").
- **`<->` KNN operator** — k-nearest projects to a point.
- **`ST_Buffer`** — site-footprint polygons for ground-mount solar, sized from the
  REPD *solar site area* where present, else derived from capacity.
- **GIST** spatial indexes on every geometry column.

## Data

- Source: [Renewable Energy Planning Database (REPD), DESNZ](https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract) — Q1 2026 quarterly extract. Open Government Licence.
- Scope loaded here: ~80 South West England projects across solar (ground/roof),
  onshore wind, battery storage, hydro and biomass, spanning four development
  stages (operational → under construction → awaiting construction → submitted).
- `db/init.sql` is generated from the REPD CSV by `scripts/build_dataset.py`
  (re-run it to refresh or widen the slice).

## Run it

**1. Start PostGIS** (loads `db/init.sql` — the REPD slice — on first boot):

```bash
docker compose up -d
```

**2. Backend:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your free GROQ_API_KEY in .env
uvicorn app.main:app --reload
```

**3. Open** http://localhost:8000 and try the example chips, e.g.
*"battery projects within 25 km of Exeter"*.

## Deploy (Fly.io)

Two apps on Fly's private network: the FastAPI app (public, TLS + `wss://`
terminated by Fly) and PostGIS (no public IP, reachable only at
`netzero-map-db.internal`).

```bash
# 1. PostGIS — deployed from the repo root so it bakes in the same db/init.sql
#    that docker-compose mounts locally.
flyctl apps create netzero-map-db
flyctl volumes create pgdata --app netzero-map-db --region lhr --size 1
flyctl secrets set POSTGRES_PASSWORD=<pw> --app netzero-map-db
flyctl deploy --config deploy/postgis/fly.toml --dockerfile deploy/postgis/Dockerfile

# 2. App
flyctl apps create netzero-map-agent
flyctl secrets set \
  GROQ_API_KEY=<key> \
  DATABASE_URL="postgresql://map:<pw>@netzero-map-db.internal:5432/map" \
  --app netzero-map-agent
flyctl deploy
```

`min_machines_running = 1` and `auto_stop_machines = false` keep it up 24/7 —
scale-to-zero would drop the websocket and put a cold start in front of the
first question. `/healthz` is the Fly health check and only passes if PostGIS
actually answers a query.

### Public-demo limits

There's no login, so the deployment protects the model key on three levels
(`backend/app/limits.py`, all tunable via `[env]` in `fly.toml`):

| Limit | Default | Why |
|---|---|---|
| Per-IP turns/minute | 5 | burst protection |
| Global turns/day | 15 | matches the free model key's real ceiling |
| Message length | 500 chars | keeps prompt size predictable |

The daily budget looks absurdly small until you measure the model tier. One
model call costs ~2.3k tokens (system prompt + ten tool schemas), and a
tool-using turn takes 2–3 calls, so a turn is ~5–7k tokens. **Groq's free tier
allows 100,000 tokens per day** — roughly **16 turns a day in total, across all
visitors**. The budget is set just under that so the app refuses politely
("hit its daily query budget") instead of leaking a raw `429`.

When the upstream limit is hit anyway, `agent.py` waits out the `retry-after`
once and then reports "the free model tier is busy". The OpenAI SDK's own retry
ladder is disabled (`max_retries=0`) — left on, it sits in backoff for minutes
and is indistinguishable from a hang.

To serve a real audience, either upgrade the Groq key to a paid tier, or point
`OPENAI_BASE_URL` at a provider with a more generous free tier (Gemini's free
tier allows ~1,500 requests/day and no daily token cap). Only two env vars
change; no code does. Raise `DAILY_TURN_BUDGET` to match.

## Map provider

The map uses **MapLibre GL JS + OpenFreeMap** so it runs with no access token.
MapLibre's API is identical to Mapbox GL JS — to switch to Mapbox, swap the two
script/style URLs in `frontend/index.html`, set `mapboxgl.accessToken`, and
rename `maplibregl` → `mapboxgl`. Nothing in the agent or tool layer changes.

## Where to extend

- **National coverage** — `scripts/build_dataset.py` filters REPD to the South
  West; drop the region filter to load all of GB and expand the `places` gazetteer.
- **Real geocoding** — `geocode_place` queries a small `places` table; swap it for
  Nominatim / Mapbox / Pelias for arbitrary places.
- **More analysis** — isochrones, routing, intersections, choropleths are all more
  PostGIS tools following the same `async def h(args, send, pool) -> str` shape.
- **Specialist sub-agents** — when the tool list gets large, route in `agent.py`.

## Layout

```
backend/app/
  main.py     FastAPI app, websocket, conversation-per-connection
  agent.py    tool-use loop + system prompt (provider-agnostic)
  tools.py    tool schemas + handlers (view + PostGIS)
  db.py       asyncpg pool
db/init.sql   PostGIS schema + REPD South West slice (generated)
scripts/
  build_dataset.py       REPD CSV -> db/init.sql
  start-postgres-mcp.sh  optional: read-only Postgres MCP for Claude Code
frontend/
  index.html  MapLibre map + chat sidebar + map-command executor
docker-compose.yml   PostGIS
```
