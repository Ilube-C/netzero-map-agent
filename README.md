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
