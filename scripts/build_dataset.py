#!/usr/bin/env python3
"""Generate db/init.sql from the public REPD dataset.

Usage:
    # 1. Download the quarterly CSV extract from DESNZ:
    #    https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract
    #    (the "...publication...csv" file), save it next to this script as repd.csv
    # 2. python scripts/build_dataset.py [path/to/repd.csv]

Public data only — no private or employer data. Coordinates are OSGB36
eastings/northings (EPSG:27700) in the source and are transformed to WGS84
(EPSG:4326) in-database by db/init.sql via PostGIS ST_Transform.

Edit REGION below (or remove the filter) to change which slice is loaded.
"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scripts" / "repd.csv"
OUT = ROOT / "db" / "init.sql"

REGION = "South West"   # set to None to load every region
PER_TECH = 16           # cap rows per technology to keep the demo dataset balanced

# --- column indices (0-based) from the REPD header --------------------------
C_REF, C_OPERATOR, C_SITE = 1, 3, 4
C_TECH, C_CAP = 5, 8
C_MOUNT = 18
C_STATUS_SHORT = 20
C_COUNTY, C_REGION, C_COUNTRY, C_POSTCODE = 24, 25, 26, 27
C_X, C_Y = 28, 29
C_SOLAR_AREA = 52

STATUS_MAP = {
    "Operational": "operational",
    "Under Construction": "under_construction",
    "Awaiting Construction": "awaiting_construction",
    "Application Submitted": "submitted",
}

BIOMASS = {
    "Biomass (dedicated)", "Biomass (co-firing)", "EfW Incineration",
    "Anaerobic Digestion", "Landfill Gas", "Sewage Sludge Digestion",
    "Advanced Conversion Technologies",
}

# SW England gazetteer: place -> (county, WGS84 lon, lat). Approximate centroids,
# used only to resolve place names in queries to a search point.
PLACES = [
    ("Bristol", "Bristol, City of", -2.59, 51.45),
    ("Avon", "Avon", -2.60, 51.42),
    ("Bath", "Bath and North East Somerset", -2.36, 51.38),
    ("Bath and North East Somerset", "Bath and North East Somerset", -2.42, 51.35),
    ("Weston-super-Mare", "North Somerset", -2.96, 51.35),
    ("North Somerset", "North Somerset", -2.77, 51.38),
    ("South Gloucestershire", "South Gloucestershire", -2.45, 51.53),
    ("Gloucestershire", "Gloucestershire", -2.20, 51.86),
    ("Gloucester", "Gloucestershire", -2.24, 51.86),
    ("Cheltenham", "Gloucestershire", -2.08, 51.90),
    ("Wiltshire", "Wiltshire", -1.99, 51.35),
    ("Swindon", "Swindon", -1.78, 51.56),
    ("Salisbury", "Wiltshire", -1.80, 51.07),
    ("Somerset", "Somerset", -2.95, 51.06),
    ("Taunton", "Somerset", -3.10, 51.02),
    ("Bridgwater", "Somerset", -3.00, 51.13),
    ("Dorset", "Dorset", -2.30, 50.75),
    ("Bournemouth", "Bournemouth, Christchurch and Poole", -1.88, 50.72),
    ("Poole", "Bournemouth, Christchurch and Poole", -1.99, 50.72),
    ("Devon", "Devon", -3.74, 50.72),
    ("Exeter", "Devon", -3.53, 50.72),
    ("Plymouth", "Plymouth", -4.14, 50.38),
    ("Torbay", "Torbay", -3.53, 50.45),
    ("Cornwall", "Cornwall", -4.65, 50.40),
    ("Truro", "Cornwall", -5.05, 50.26),
]


def map_tech(tech: str, mount: str):
    t = tech.strip()
    if t == "Solar Photovoltaics":
        return "solar_rooftop" if "roof" in mount.lower() else "solar_ground"
    if t == "Wind Onshore":
        return "wind"
    if t == "Battery":
        return "bess"
    if t in ("Large Hydro", "Small Hydro"):
        return "hydro"
    if t in BIOMASS:
        return "biomass"
    return None


def sql_str(v):
    if v is None or v == "":
        return "NULL"
    return "'" + str(v).replace("'", "''").strip() + "'"


def main():
    if not SRC.exists():
        sys.exit(f"REPD CSV not found at {SRC}. See the docstring for the download link.")

    rows = []
    with open(SRC, encoding="latin-1") as fh:
        r = csv.reader(fh)
        next(r)  # header
        for row in r:
            if len(row) <= C_SOLAR_AREA:
                continue
            if REGION and row[C_REGION].strip() != REGION:
                continue
            if row[C_COUNTRY].strip() != "England":
                continue
            tech = map_tech(row[C_TECH], row[C_MOUNT])
            status = STATUS_MAP.get(row[C_STATUS_SHORT].strip())
            if not tech or not status:
                continue
            try:
                cap = float(row[C_CAP])
                x = float(row[C_X]); y = float(row[C_Y])
            except ValueError:
                continue
            if cap <= 0 or x <= 0 or y <= 0:
                continue
            try:
                area_ha = round(float(row[C_SOLAR_AREA]) / 10000.0, 2) if row[C_SOLAR_AREA] else None
            except ValueError:
                area_ha = None
            rows.append({
                "ref": row[C_REF].strip(), "title": row[C_SITE].strip(),
                "operator": row[C_OPERATOR].strip(), "tech": tech, "cap": cap,
                "status": status, "county": row[C_COUNTY].strip(),
                "region": row[C_REGION].strip(), "postcode": row[C_POSTCODE].strip(),
                "x": x, "y": y, "area_ha": area_ha,
            })

    by_tech = {}
    for row in sorted(rows, key=lambda d: -d["cap"]):
        by_tech.setdefault(row["tech"], []).append(row)
    picked = []
    for items in by_tech.values():
        picked.extend(items[:PER_TECH])
    picked.sort(key=lambda d: (d["tech"], -d["cap"]))

    print(f"candidate rows: {len(rows)}  ->  picked: {len(picked)}", file=sys.stderr)
    print("by technology:", dict(Counter(p["tech"] for p in picked)), file=sys.stderr)
    print("by status:    ", dict(Counter(p["status"] for p in picked)), file=sys.stderr)

    with open(OUT, "w") as out:
        w = out.write
        w("-- Renewable-energy projects across South West England.\n")
        w("-- PUBLIC DATA: DESNZ Renewable Energy Planning Database (REPD).\n")
        w("-- https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract\n")
        w("-- Generated by scripts/build_dataset.py — do not edit by hand.\n")
        w("-- Coordinates are OSGB36 (EPSG:27700) in the source and are transformed to\n")
        w("-- WGS84 (EPSG:4326) here with PostGIS ST_Transform.\n\n")
        w("CREATE EXTENSION IF NOT EXISTS postgis;\n\n")

        w("DROP TABLE IF EXISTS places;\n")
        w("CREATE TABLE places (\n"
          "    id     serial PRIMARY KEY,\n"
          "    name   text NOT NULL,\n"
          "    county text,\n"
          "    geom   geometry(Point, 4326) NOT NULL\n);\n")
        w("CREATE INDEX places_geom_idx ON places USING GIST (geom);\n\n")
        w("INSERT INTO places (name, county, geom) VALUES\n")
        w(",\n".join(
            f"    ({sql_str(n)}, {sql_str(c)}, ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326))"
            for n, c, lon, lat in PLACES) + ";\n\n")

        w("DROP TABLE IF EXISTS projects;\n")
        w("CREATE TABLE projects (\n"
          "    id                 serial PRIMARY KEY,\n"
          "    ref_id             text,\n"
          "    title              text NOT NULL,\n"
          "    operator           text,\n"
          "    technology         text NOT NULL,  -- solar_ground|solar_rooftop|wind|bess|hydro|biomass\n"
          "    capacity_mw        numeric,\n"
          "    status             text NOT NULL,  -- operational|under_construction|awaiting_construction|submitted\n"
          "    county             text,\n"
          "    region             text,\n"
          "    postcode           text,\n"
          "    geo_precision      text NOT NULL DEFAULT 'exact_site',\n"
          "    site_area_hectares numeric,\n"
          "    easting            numeric,\n"
          "    northing           numeric,\n"
          "    geom               geometry(Point, 4326) NOT NULL,\n"
          "    footprint          geometry(Polygon, 4326)\n);\n")
        w("CREATE INDEX projects_geom_idx ON projects USING GIST (geom);\n\n")

        w("INSERT INTO projects\n"
          "    (ref_id, title, operator, technology, capacity_mw, status, county, region,\n"
          "     postcode, site_area_hectares, easting, northing, geom)\n")
        w("SELECT ref_id, title, operator, technology, capacity_mw, status, county, region,\n"
          "       postcode, site_area_hectares, easting, northing,\n"
          "       ST_Transform(ST_SetSRID(ST_MakePoint(easting, northing), 27700), 4326)\n")
        w("FROM (VALUES\n")
        body = []
        for p in picked:
            body.append(
                f"    ({sql_str(p['ref'])}, {sql_str(p['title'])}, {sql_str(p['operator'])}, "
                f"{sql_str(p['tech'])}, {p['cap']}, {sql_str(p['status'])}, {sql_str(p['county'])}, "
                f"{sql_str(p['region'])}, {sql_str(p['postcode'])}, "
                f"{p['area_ha'] if p['area_ha'] is not None else 'NULL'}, {p['x']}, {p['y']})")
        w(",\n".join(body) + "\n")
        w(") AS v(ref_id, title, operator, technology, capacity_mw, status, county, region,\n"
          "       postcode, site_area_hectares, easting, northing);\n\n")

        w("UPDATE projects\n"
          "SET site_area_hectares = round((capacity_mw * 0.8)::numeric, 1)\n"
          "WHERE technology = 'solar_ground' AND site_area_hectares IS NULL AND capacity_mw IS NOT NULL;\n\n")
        w("UPDATE projects\n"
          "SET footprint = ST_Buffer(geom::geography, sqrt(site_area_hectares * 10000 / pi()))::geometry\n"
          "WHERE technology = 'solar_ground' AND site_area_hectares IS NOT NULL;\n")

    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
