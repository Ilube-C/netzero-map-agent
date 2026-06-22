"""Tool definitions and handlers for the renewable-energy projects map agent.

Two conceptual kinds of tool share one interface:

  * VIEW tools  — manipulate the MapLibre/Mapbox view (camera, styling, clear).
  * DATA tools  — run PostGIS queries over the `projects` table and render the
                  result as a styled layer, returning a COMPACT text summary to
                  the model (counts / MW / breakdown), never raw geometry.

Every handler has the signature:  async def h(args, send, pool) -> str
where `send(command: dict)` ships one message to the browser.

Spatial tools accept a `place`/`area` NAME and geocode it server-side, so the
model never copies coordinates between calls (its main weak-model failure mode).

Data is the public DESNZ Renewable Energy Planning Database (REPD); coordinates
were transformed from OSGB36 to WGS84 in-database at load time (see db/init.sql).
"""
import json
import re
from typing import Any, Awaitable, Callable

import asyncpg

Send = Callable[[dict], Awaitable[None]]

TECHNOLOGIES = ["solar_ground", "solar_rooftop", "wind", "bess", "hydro", "biomass"]
STATUSES = ["operational", "under_construction", "awaiting_construction", "submitted"]

TECH_COLOR = {
    "solar_ground": "#f1c40f",
    "solar_rooftop": "#f39c12",
    "wind": "#3498db",
    "bess": "#9b59b6",
    "hydro": "#1abc9c",
    "biomass": "#2ecc71",
}

# Columns selected for every project feature.
_PROJ_COLS = (
    "id, ref_id, title, operator, technology, capacity_mw, status, county, "
    "geo_precision, ST_AsGeoJSON(geom) AS gj"
)


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _flatten_coords(geom: Any):
    if isinstance(geom, (list, tuple)):
        if geom and isinstance(geom[0], (int, float)):
            yield geom[0], geom[1]
        else:
            for sub in geom:
                yield from _flatten_coords(sub)


def _bbox(features: list[dict]) -> list[float] | None:
    xs, ys = [], []
    for f in features:
        for lon, lat in _flatten_coords(f["geometry"]["coordinates"]):
            xs.append(lon)
            ys.append(lat)
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _point(lon: float, lat: float) -> str:
    return f"ST_SetSRID(ST_MakePoint({float(lon)}, {float(lat)}), 4326)"


async def _fit(send: Send, features: list[dict]) -> None:
    box = _bbox(features)
    if box:
        await send({"type": "map_command", "command": "fit_bounds", "args": {"bbox": box}})


# --------------------------------------------------------------------------- #
# Geocoding (place / area names -> coordinates and county)
# --------------------------------------------------------------------------- #
_STOPWORDS = {"the", "of", "council", "district", "area", "in", "near", "and", "county"}


async def _geocode_row(pool: asyncpg.Pool, query: str):
    sql = ("SELECT name, county, ST_X(geom) AS lon, ST_Y(geom) AS lat "
           "FROM places WHERE name ILIKE $1 ORDER BY length(name) LIMIT 1")
    row = await pool.fetchrow(sql, f"%{query.strip()}%")
    if row:
        return row
    for word in [w for w in re.findall(r"[A-Za-z]+", query) if w.lower() not in _STOPWORDS]:
        row = await pool.fetchrow(sql, f"%{word}%")
        if row:
            return row
    return None


async def _resolve_point(args: dict, pool: asyncpg.Pool) -> tuple[float, float, str | None]:
    if args.get("place"):
        row = await _geocode_row(pool, args["place"])
        if not row:
            raise ValueError(f"Could not find a place matching '{args['place']}'.")
        return float(row["lon"]), float(row["lat"]), row["name"]
    if args.get("longitude") is not None and args.get("latitude") is not None:
        return float(args["longitude"]), float(args["latitude"]), None
    raise ValueError("Provide either a 'place' name or both 'longitude' and 'latitude'.")


async def _resolve_county(pool: asyncpg.Pool, text: str) -> str | None:
    row = await _geocode_row(pool, text)
    return row["county"] if row else None


_PROJ_STOPWORDS = {"farm", "project", "scheme", "site", "the", "of", "and", "a", "an",
                   "battery", "storage", "solar", "energy", "system"}


async def _match_project_id(pool: asyncpg.Pool, query: str) -> int | None:
    """Resolve a free-text project reference to an id. Tries a substring match,
    then falls back to best word-overlap so a partial title still matches."""
    row = await pool.fetchrow(
        "SELECT id FROM projects WHERE title ILIKE $1 ORDER BY length(title) LIMIT 1",
        f"%{query.strip()}%")
    if row:
        return row["id"]
    words = [w for w in re.findall(r"[A-Za-z]+", query)
             if w.lower() not in _PROJ_STOPWORDS and len(w) > 2]
    if not words:
        return None
    row = await pool.fetchrow(
        "SELECT id, (SELECT count(*) FROM unnest($1::text[]) w WHERE title ILIKE '%'||w||'%') "
        "AS score FROM projects ORDER BY score DESC, length(title) LIMIT 1", words)
    return row["id"] if row and row["score"] > 0 else None


# --------------------------------------------------------------------------- #
# Project rendering + filters
# --------------------------------------------------------------------------- #
def _proj_feature(r) -> dict:
    mw = float(r["capacity_mw"]) if r["capacity_mw"] is not None else None
    return {
        "type": "Feature",
        "properties": {
            "id": r["id"],
            "ref_id": r["ref_id"],
            "title": r["title"],
            "operator": r["operator"],
            "technology": r["technology"],
            "capacity_mw": mw,
            "status": r["status"],
            "county": r["county"],
            "geo_precision": r["geo_precision"],
            "color": TECH_COLOR.get(r["technology"], "#888888"),
        },
        "geometry": json.loads(r["gj"]),
    }


async def _render_projects(send: Send, layer_id: str, features: list[dict],
                           fit: bool = True) -> None:
    await send({"type": "map_command", "command": "add_projects",
                "args": {"layer_id": layer_id, "geojson": _fc(features)}})
    if fit:
        await _fit(send, features)


async def _build_filters(args: dict, pool: asyncpg.Pool) -> tuple[list[str], list]:
    """Return (clauses, params) for the optional project filters."""
    clauses: list[str] = []
    params: list = []

    def add(cond: str, val) -> None:
        params.append(val)
        clauses.append(cond.format(i=len(params)))

    tech = args.get("technology")
    if tech == "solar":  # family alias -> both solar technologies in one query
        clauses.append("technology IN ('solar_ground', 'solar_rooftop')")
    elif tech:
        add("technology = ${i}", tech)
    if args.get("status"):
        add("status = ${i}", args["status"])
    if args.get("min_capacity_mw") is not None:
        add("capacity_mw >= ${i}", float(args["min_capacity_mw"]))
    if args.get("area"):
        county = await _resolve_county(pool, args["area"])
        if county:
            add("county = ${i}", county)
        else:
            add("county ILIKE ${i}", f"%{args['area']}%")
    return clauses, params


def _summary(rows, headline: str) -> str:
    n = len(rows)
    if n == 0:
        return f"No projects match {headline}."
    total_mw = sum(float(r["capacity_mw"]) for r in rows if r["capacity_mw"] is not None)
    by_tech: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_tech[r["technology"]] = by_tech.get(r["technology"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    tech_bd = ", ".join(f"{c}× {t}" for t, c in sorted(by_tech.items()))
    status_bd = ", ".join(f"{c} {s.replace('_', ' ')}" for s, c in sorted(by_status.items()))
    return (f"{n} project{'' if n == 1 else 's'} {headline} — "
            f"{total_mw:.1f} MW total ({tech_bd}). By stage: {status_bd}.")


# --------------------------------------------------------------------------- #
# DATA tools
# --------------------------------------------------------------------------- #
async def search_projects(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    clauses, params = await _build_filters(args, pool)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = int(args.get("limit", 200))
    rows = await pool.fetch(
        f"SELECT {_PROJ_COLS} FROM projects {where} "
        f"ORDER BY capacity_mw DESC NULLS LAST LIMIT {limit}",
        *params,
    )
    feats = [_proj_feature(r) for r in rows]
    await _render_projects(send, "projects", feats)
    return _summary(rows, "matching your filters")


async def projects_within_distance(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    lon, lat, place = await _resolve_point(args, pool)
    meters = float(args["radius_meters"])
    clauses, params = await _build_filters(args, pool)
    params.append(meters)
    clauses.append(f"ST_DWithin(geom::geography, {_point(lon, lat)}::geography, ${len(params)})")
    rows = await pool.fetch(
        f"SELECT {_PROJ_COLS} FROM projects WHERE {' AND '.join(clauses)} "
        f"ORDER BY capacity_mw DESC NULLS LAST",
        *params,
    )
    feats = [_proj_feature(r) for r in rows]
    # Show the search radius as a translucent circle behind the results.
    circle = await pool.fetchval(
        f"SELECT ST_AsGeoJSON(ST_Buffer({_point(lon, lat)}::geography, $1)::geometry)", meters)
    await send({"type": "map_command", "command": "add_geojson_layer",
                "args": {"layer_id": "search_radius",
                         "geojson": _fc([{"type": "Feature", "properties": {},
                                          "geometry": json.loads(circle)}]),
                         "geom_type": "fill", "color": "#3498db"}})
    await _render_projects(send, "projects", feats)
    where = f"within {meters / 1000:.0f} km of {place}" if place else f"within {meters:.0f} m"
    return _summary(rows, where)


async def nearest_projects(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    lon, lat, place = await _resolve_point(args, pool)
    k = int(args.get("k", 5))
    clauses, params = await _build_filters(args, pool)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await pool.fetch(
        f"SELECT {_PROJ_COLS} FROM projects {where} "
        f"ORDER BY geom <-> {_point(lon, lat)} LIMIT {k}",
        *params,
    )
    feats = [_proj_feature(r) for r in rows]
    await _render_projects(send, "projects", feats)
    return _summary(rows, f"nearest to {place}" if place else "nearest to the point")


async def area_summary(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    clauses, params = await _build_filters(args, pool)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await pool.fetch(
        f"SELECT county, count(*) AS n, round(coalesce(sum(capacity_mw),0),1) AS mw "
        f"FROM projects {where} GROUP BY county ORDER BY mw DESC",
        *params)
    # Render every matching project, coloured by technology as usual.
    proj_rows = await pool.fetch(
        f"SELECT {_PROJ_COLS} FROM projects {where}", *params)
    await _render_projects(send, "projects", [_proj_feature(r) for r in proj_rows])
    lines = "; ".join(f"{r['county']}: {r['n']} ({r['mw']} MW)" for r in rows)
    return f"By county — {lines}."


async def show_footprint(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    proj_id = await _match_project_id(pool, args["project"])
    if proj_id is None:
        return f"No project matching '{args['project']}'."
    row = await pool.fetchrow(
        "SELECT title, site_area_hectares, ST_AsGeoJSON(footprint) AS gj "
        "FROM projects WHERE id = $1", proj_id)
    if not row["gj"]:
        return (f"'{row['title']}' has no footprint — footprints are only derived for "
                f"ground-mount solar in this dataset.")
    poly = {"type": "Feature", "properties": {}, "geometry": json.loads(row["gj"])}
    await send({"type": "map_command", "command": "add_geojson_layer",
                "args": {"layer_id": "footprint", "geojson": _fc([poly]),
                         "geom_type": "fill", "color": "#f1c40f"}})
    await _fit(send, [poly])
    return f"{row['title']} footprint ≈ {row['site_area_hectares']} ha (layer 'footprint')."


async def geocode_place(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    row = await _geocode_row(pool, args["query"])
    if not row:
        return f"No place matching '{args['query']}'."
    county = f" (county: {row['county']})" if row["county"] else ""
    return f"{row['name']} is at longitude {row['lon']:.5f}, latitude {row['lat']:.5f}{county}."


# --------------------------------------------------------------------------- #
# VIEW tools
# --------------------------------------------------------------------------- #
async def fly_to(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    lon, lat, place = await _resolve_point(args, pool)
    zoom = float(args.get("zoom", 12))
    await send({"type": "map_command", "command": "fly_to",
                "args": {"longitude": lon, "latitude": lat, "zoom": zoom}})
    return f"Flew to {place or f'({lon:.5f}, {lat:.5f})'}."


async def set_layer_color(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    await send({"type": "map_command", "command": "set_layer_color",
                "args": {"layer_id": args["layer_id"], "color": args["color"]}})
    return f"Recoloured layer '{args['layer_id']}'."


async def set_layer_visibility(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    await send({"type": "map_command", "command": "set_layer_visibility",
                "args": {"layer_id": args["layer_id"], "visible": bool(args["visible"])}})
    return f"Set layer '{args['layer_id']}' visibility to {bool(args['visible'])}."


async def clear_map(args: dict, send: Send, pool: asyncpg.Pool) -> str:
    await send({"type": "map_command", "command": "clear", "args": {}})
    return "Cleared the map."


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
HANDLERS: dict[str, Callable[..., Awaitable[str]]] = {
    "search_projects": search_projects,
    "projects_within_distance": projects_within_distance,
    "nearest_projects": nearest_projects,
    "area_summary": area_summary,
    "show_footprint": show_footprint,
    "geocode_place": geocode_place,
    "fly_to": fly_to,
    "set_layer_color": set_layer_color,
    "set_layer_visibility": set_layer_visibility,
    "clear_map": clear_map,
}

_lonlat = {
    "longitude": {"type": "number", "description": "Longitude (WGS84). Only when no place name is used."},
    "latitude": {"type": "number", "description": "Latitude (WGS84). Only when no place name is used."},
}
_place_prop = {
    "type": "string",
    "description": "A place/town/county in SW England (e.g. 'Bath', 'Bristol', 'Devon'). Geocoded server-side.",
}
_filter_props = {
    "technology": {"type": "string", "enum": TECHNOLOGIES + ["solar"],
                   "description": "Use 'solar' to mean both ground- and rooftop-mounted solar."},
    "status": {"type": "string", "enum": STATUSES,
               "description": "Development stage: operational | under_construction | awaiting_construction | submitted"},
    "area": {"type": "string", "description": "County or place name, e.g. 'Devon', 'Wiltshire', 'Bath'."},
    "min_capacity_mw": {"type": "number", "description": "Only projects at least this many MW."},
}

TOOLS: list[dict] = [
    {
        "name": "search_projects",
        "description": "Find renewable-energy projects, optionally filtered by technology, "
                       "development status, county/area, and minimum capacity, and render them "
                       "on the map (colour = technology, size = MW).",
        "input_schema": {
            "type": "object",
            "properties": {**_filter_props, "limit": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "projects_within_distance",
        "description": "Find projects within a radius (metres) of a place, with the same "
                       "optional filters. Renders the search radius too. Uses PostGIS ST_DWithin.",
        "input_schema": {
            "type": "object",
            "properties": {"place": _place_prop, **_lonlat,
                           "radius_meters": {"type": "number"}, **_filter_props},
            "required": ["radius_meters"],
        },
    },
    {
        "name": "nearest_projects",
        "description": "Find the k projects nearest to a place (PostGIS KNN), with the "
                       "same optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {"place": _place_prop, **_lonlat,
                           "k": {"type": "integer", "description": "How many (default 5)"},
                           **_filter_props},
            "required": [],
        },
    },
    {
        "name": "area_summary",
        "description": "Aggregate projects by county (count and total MW), optionally "
                       "filtered, and render the matching projects.",
        "input_schema": {
            "type": "object",
            "properties": {**_filter_props},
            "required": [],
        },
    },
    {
        "name": "show_footprint",
        "description": "Render the site footprint polygon for a ground-mount solar project "
                       "(area from REPD solar site area, or derived from capacity).",
        "input_schema": {
            "type": "object",
            "properties": {"project": {"type": "string",
                           "description": "Project title or part of it."}},
            "required": ["project"],
        },
    },
    {
        "name": "geocode_place",
        "description": "Resolve a place/county name to coordinates and its county. Use only "
                       "when the user explicitly wants coordinates; for spatial queries pass "
                       "the place name straight to the tool above.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "fly_to",
        "description": "Move the map camera to a place (preferred) or explicit coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {"place": _place_prop, **_lonlat,
                           "zoom": {"type": "number", "description": "Zoom 0-20 (default 12)"}},
            "required": [],
        },
    },
    {
        "name": "set_layer_color",
        "description": "Change the colour of an existing layer (e.g. 'projects', 'footprint').",
        "input_schema": {
            "type": "object",
            "properties": {"layer_id": {"type": "string"},
                           "color": {"type": "string", "description": "CSS/hex colour"}},
            "required": ["layer_id", "color"],
        },
    },
    {
        "name": "set_layer_visibility",
        "description": "Show or hide an existing layer by id.",
        "input_schema": {
            "type": "object",
            "properties": {"layer_id": {"type": "string"}, "visible": {"type": "boolean"}},
            "required": ["layer_id", "visible"],
        },
    },
    {
        "name": "clear_map",
        "description": "Remove all layers and markers from the map.",
        "input_schema": {"type": "object", "properties": {}},
    },
]
