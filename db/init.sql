-- Renewable-energy projects across South West England.
-- PUBLIC DATA: DESNZ Renewable Energy Planning Database (REPD), Q1 2026.
-- https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract
-- Coordinates are OSGB36 (EPSG:27700) eastings/northings in the source and are
-- transformed to WGS84 (EPSG:4326) here with PostGIS ST_Transform.

CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS places;
CREATE TABLE places (
    id     serial PRIMARY KEY,
    name   text NOT NULL,
    county text,
    geom   geometry(Point, 4326) NOT NULL
);
CREATE INDEX places_geom_idx ON places USING GIST (geom);

INSERT INTO places (name, county, geom) VALUES
    ('Bristol', 'Bristol, City of', ST_SetSRID(ST_MakePoint(-2.59, 51.45), 4326)),
    ('Avon', 'Avon', ST_SetSRID(ST_MakePoint(-2.6, 51.42), 4326)),
    ('Bath', 'Bath and North East Somerset', ST_SetSRID(ST_MakePoint(-2.36, 51.38), 4326)),
    ('Bath and North East Somerset', 'Bath and North East Somerset', ST_SetSRID(ST_MakePoint(-2.42, 51.35), 4326)),
    ('Weston-super-Mare', 'North Somerset', ST_SetSRID(ST_MakePoint(-2.96, 51.35), 4326)),
    ('North Somerset', 'North Somerset', ST_SetSRID(ST_MakePoint(-2.77, 51.38), 4326)),
    ('South Gloucestershire', 'South Gloucestershire', ST_SetSRID(ST_MakePoint(-2.45, 51.53), 4326)),
    ('Gloucestershire', 'Gloucestershire', ST_SetSRID(ST_MakePoint(-2.2, 51.86), 4326)),
    ('Gloucester', 'Gloucestershire', ST_SetSRID(ST_MakePoint(-2.24, 51.86), 4326)),
    ('Cheltenham', 'Gloucestershire', ST_SetSRID(ST_MakePoint(-2.08, 51.9), 4326)),
    ('Wiltshire', 'Wiltshire', ST_SetSRID(ST_MakePoint(-1.99, 51.35), 4326)),
    ('Swindon', 'Swindon', ST_SetSRID(ST_MakePoint(-1.78, 51.56), 4326)),
    ('Salisbury', 'Wiltshire', ST_SetSRID(ST_MakePoint(-1.8, 51.07), 4326)),
    ('Somerset', 'Somerset', ST_SetSRID(ST_MakePoint(-2.95, 51.06), 4326)),
    ('Taunton', 'Somerset', ST_SetSRID(ST_MakePoint(-3.1, 51.02), 4326)),
    ('Bridgwater', 'Somerset', ST_SetSRID(ST_MakePoint(-3.0, 51.13), 4326)),
    ('Dorset', 'Dorset', ST_SetSRID(ST_MakePoint(-2.3, 50.75), 4326)),
    ('Bournemouth', 'Bournemouth, Christchurch and Poole', ST_SetSRID(ST_MakePoint(-1.88, 50.72), 4326)),
    ('Poole', 'Bournemouth, Christchurch and Poole', ST_SetSRID(ST_MakePoint(-1.99, 50.72), 4326)),
    ('Devon', 'Devon', ST_SetSRID(ST_MakePoint(-3.74, 50.72), 4326)),
    ('Exeter', 'Devon', ST_SetSRID(ST_MakePoint(-3.53, 50.72), 4326)),
    ('Plymouth', 'Plymouth', ST_SetSRID(ST_MakePoint(-4.14, 50.38), 4326)),
    ('Torbay', 'Torbay', ST_SetSRID(ST_MakePoint(-3.53, 50.45), 4326)),
    ('Cornwall', 'Cornwall', ST_SetSRID(ST_MakePoint(-4.65, 50.4), 4326)),
    ('Truro', 'Cornwall', ST_SetSRID(ST_MakePoint(-5.05, 50.26), 4326));

DROP TABLE IF EXISTS projects;
CREATE TABLE projects (
    id                 serial PRIMARY KEY,
    ref_id             text,
    title              text NOT NULL,
    operator           text,
    technology         text NOT NULL,  -- solar_ground|solar_rooftop|wind|bess|hydro|biomass
    capacity_mw        numeric,
    status             text NOT NULL,  -- operational|under_construction|awaiting_construction|submitted
    county             text,
    region             text,
    postcode           text,
    geo_precision      text NOT NULL DEFAULT 'exact_site',
    site_area_hectares numeric,
    easting            numeric,
    northing           numeric,
    geom               geometry(Point, 4326) NOT NULL,
    footprint          geometry(Polygon, 4326)
);
CREATE INDEX projects_geom_idx ON projects USING GIST (geom);

INSERT INTO projects
    (ref_id, title, operator, technology, capacity_mw, status, county, region,
     postcode, site_area_hectares, easting, northing, geom)
SELECT ref_id, title, operator, technology, capacity_mw, status, county, region,
       postcode, site_area_hectares, easting, northing,
       ST_Transform(ST_SetSRID(ST_MakePoint(easting, northing), 27700), 4326)
FROM (VALUES
    ('18670', 'Brockleaze, Neston Park Estate - Battery Energy Storage', 'Grenergy Renewables UK Limited', 'bess', 450.0, 'submitted', 'Wiltshire', 'South West', 'SN13 9PQ', NULL, 387350.0, 167957.0),
    ('12651', 'East Chickerell Court Farm - Battery Energy Storage System', 'Statera Energy', 'bess', 400.0, 'awaiting_construction', 'Dorset', 'South West', 'DT3 4BG', NULL, 365414.0, 81099.0),
    ('14935', 'Junction 27, Westleigh - Battery Storage', 'Clearstone Energy', 'bess', 400.0, 'awaiting_construction', 'Devon', 'South West', 'EX16 7ES', NULL, 305163.0, 116749.0),
    ('13980', 'Saundercroft Farm - Battery Energy Storage System', 'Exeter Storage Limited (Statera Energy)', 'bess', 290.0, 'awaiting_construction', 'Devon', 'South West', 'EX5 2PF', NULL, 301447.0, 96995.0),
    ('13607', 'Westerleigh Hill, Westerleigh - Battery Energy Storage Facility', 'Immersa Limited', 'bess', 200.0, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS37 8RD', NULL, 369350.0, 178568.0),
    ('13643', 'Earthcott Green Farm, Earthcott Green - Battery Energy Storage', 'Immersa Limited', 'bess', 200.0, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS35 3TD', NULL, 364765.0, 185134.0),
    ('11612', 'Norrington Gate Farm, Broughton Gifford - Battery Energy Storage Facility', 'ADV 003 Limited', 'bess', 150.0, 'awaiting_construction', 'Wiltshire', 'South West', 'SN12 8LW', NULL, 388184.0, 164072.0),
    ('17747', 'Exeter Substation, Broadclyst - Battery Energy Storage', 'Broadclyst Energy Storage Limited', 'bess', 125.0, 'submitted', 'Devon', 'South West', 'EX5 3DB', NULL, 301724.0, 97732.0),
    ('10626', 'Shaftesbury Energy Park - Battery Storage System', 'TagEnergy', 'bess', 100.0, 'awaiting_construction', 'Dorset', 'South West', 'SP7 9NP', NULL, 385168.0, 123811.0),
    ('17484', 'National Grid Substation - Battery Energy Storage System', 'Penso Power (BW ESS)', 'bess', 100.0, 'awaiting_construction', 'Devon', 'South West', 'EX5 3DA', NULL, 300443.0, 97423.0),
    ('18361', 'Gammaton Barton Farm, Alverdiscott - Battery Energy Storage', 'Torridge District Council', 'bess', 100.0, 'awaiting_construction', 'Devon', 'South West', 'EX39 4QA', NULL, 248621.0, 125438.0),
    ('19207', 'Station Road & Nye Road, Sandford - Battery Energy Storage System', 'Aura Power Developments Limited', 'bess', 100.0, 'submitted', 'Somerset', 'South West', 'BS25 5QE', NULL, 342004.0, 159903.0),
    ('13145', 'Linton Court Farm, Highnam - Battery storage', 'STOR 136 Limited', 'bess', 99.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL2 8DF', NULL, 380221.0, 219109.0),
    ('14076', 'Lower Larks Farm - Battery storage', 'IPP Cero Generation', 'bess', 99.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS37 9TX', NULL, 366774.0, 185689.0),
    ('20307', 'West Webbery Farm, The Water - Battery Energy Storage', 'Enray SPV 241491 Limited', 'bess', 99.4, 'submitted', 'Devon', 'South West', 'EX39 4PP', NULL, 249077.0, 125936.0),
    ('14722', 'Iron Acton Substation, Latteridge Lane - Battery Energy Storage System', 'Balance Power Projects Limited', 'bess', 99.0, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS35 3TF', NULL, 366403.0, 185573.0),
    ('1008', 'Avonmouth Resource Recovery Centre (formerly Severn Road)', 'Viridor', 'biomass', 34.0, 'operational', 'Avon', 'South West', 'BS11 0YU', NULL, 353850.0, 181366.0),
    ('918', 'Severnside Energy Recovery Centre', 'SITA UK', 'biomass', 32.0, 'operational', 'Avon', 'South West', 'BS10 7SP', NULL, 354653.0, 182612.0),
    ('941', 'North Yard EfW', 'MVV Environment', 'biomass', 22.5, 'operational', 'Devon', 'South West', 'PL2 2DQ', NULL, 244810.0, 57524.0),
    ('914', 'Cornwall ERC', 'SUEZ', 'biomass', 20.0, 'operational', 'Cornwall', 'South West', 'PL26 8DY', NULL, 194637.0, 56502.0),
    ('9511', 'Portland Energy Recovery Facility', 'Powerfuel Power Plc', 'biomass', 15.2, 'awaiting_construction', 'Dorset', 'South West', 'DT5 1PP', NULL, 368998.0, 74438.0),
    ('998', 'Javelin Park EfW', 'Urbaser Balfour Beatty', 'biomass', 14.5, 'operational', 'Gloucestershire', 'South West', NULL, NULL, 380048.0, 210468.0),
    ('6028', 'Keypoint Industrial Estate', 'Rolton Group', 'biomass', 14.5, 'awaiting_construction', 'Wiltshire', 'South West', 'SN3 4RY', NULL, 418568.0, 186806.0),
    ('939', 'Exeter EfW', 'Viridor', 'biomass', 13.0, 'operational', 'Devon', 'South West', 'EX2 8QE', NULL, 292605.0, 90422.0),
    ('232', 'Bristol STW (Waste AD)', 'GENeco', 'biomass', 10.0, 'operational', 'Avon', 'South West', 'BS11 0YS', NULL, 353600.0, 179530.0),
    ('956', 'Canford', 'Syngas Products/ Canford Renewable Energy Ltd', 'biomass', 10.0, 'under_construction', 'Dorset', 'South West', NULL, NULL, 403439.0, 96722.0),
    ('6257', 'Showground Road', 'Bridgwater Resource Recovery', 'biomass', 7.8, 'under_construction', 'Somerset', 'South West', 'TA6 6AJ', NULL, 330970.0, 135064.0),
    ('8242', 'Showground Road, Bridgwater Energy Recovery Facility', 'Bridgwater Resource Recovery Limited', 'biomass', 7.75, 'submitted', 'Somerset', 'South West', 'TA6 6AJ', NULL, 330970.0, 135064.0),
    ('915', 'Avonmouth', 'Avonmouth Biopower', 'biomass', 6.5, 'operational', 'Avon', 'South West', NULL, NULL, 352153.0, 179196.0),
    ('1014', 'Avonmouth Low Carbon Energy Facility - Phase 2', 'Avonmouth Biopower', 'biomass', 6.5, 'operational', 'Avon', 'South West', NULL, NULL, 352153.0, 179196.0),
    ('586', 'Whites Landfill Site (Canford)', 'Canford Renewable Energy Ltd', 'biomass', 6.0, 'operational', 'Dorset', 'South West', NULL, NULL, 403000.0, 96500.0),
    ('6396', 'Swindon Energy Plant (Park Grounds)', 'Advanced Biofuel Solutions (formerly Crapper and Sons Landfill)', 'biomass', 6.0, 'under_construction', 'Wiltshire', 'South West', 'SN4 8DW', NULL, 405117.0, 183986.0),
    ('17875', 'Court Farm Business Park, Road To Court Farm - Hydroelectric System', 'Court Farm Business Park', 'hydro', 10.0, 'operational', 'Dorset', 'South West', 'DT2 7BT', NULL, 368556.0, 104810.0),
    ('15898', 'Headon Works, Cornwood - Hydro Energy Storage Facility', 'SCR-Sibelco', 'hydro', 0.5, 'awaiting_construction', 'Devon', 'South West', 'PL21 9PW', NULL, 258493.0, 60364.0),
    ('8051', 'Larks Green Solar Farm', 'Enso Energy / Iron Acton Green', 'solar_ground', 70.0, 'operational', 'Gloucestershire', 'South West', 'BS37 9TX', 106.0, 367014.0, 186672.0),
    ('2203', 'Bradenstoke solar park', 'Defence Infrastructure Organisation / BSR', 'solar_ground', 69.8, 'operational', 'Wiltshire', 'South West', 'SN15 4XX', 90.0, 402315.0, 178635.0),
    ('9456', 'Coldharbour Farm, Ashreigney - Solar Photovoltaic Array', 'Coldharbour Solar Park Limited', 'solar_ground', 49.99, 'submitted', 'Devon', 'South West', 'EX18 7NQ', 59.56, 260578.0, 112719.0),
    ('19452', 'Yew Tree Farm, Yew Tree Lane - Solar Farm', 'Yew Tree Farm Solar Limited', 'solar_ground', 49.99, 'awaiting_construction', 'North Somerset', 'South West', 'BS21 6XG', 88.3, 339812.0, 166436.0),
    ('7519', 'Corner Copse Solar Farm', 'BayWa r.e. UK Limited', 'solar_ground', 49.9, 'under_construction', 'Wiltshire', 'South West', 'SN6', 95.52, 418268.0, 190691.0),
    ('7616', 'Down Barn Farm', 'Scottish Power Renewables', 'solar_ground', 49.9, 'awaiting_construction', 'Wiltshire', 'South West', 'SP4 0EH', 93.7, 422070.0, 143863.0),
    ('7944', 'Perrinpit Farm', 'Grune Energien', 'solar_ground', 49.9, 'under_construction', 'Gloucestershire', 'South West', 'BS36 2AT', 90.0, 365642.0, 183051.0),
    ('8038', 'Claydon Farm - Solar Farm & Battery Storage', 'JBM Solar Projects 17 Limited', 'solar_ground', 49.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL20 7BH', 106.74, 393239.0, 231474.0),
    ('8062', 'Wick Farm Melksham Substation', 'JBM Solar Projects', 'solar_ground', 49.9, 'under_construction', 'Wiltshire', 'South West', 'SN15 2LU', 96.32, 390480.0, 167478.0),
    ('8101', 'Litchardon Cross Solar Farm', 'Aura Power / Infinis Energy Services', 'solar_ground', 49.9, 'operational', 'Devon', 'South West', 'EX31 3QE', 36.6, 251416.0, 129455.0),
    ('8136', 'Kemble Wick', 'Aura Power', 'solar_ground', 49.9, 'operational', 'Gloucestershire', 'South West', 'GL7 6EH', 19.78, 397998.0, 195730.0),
    ('8323', 'Stowey Road, Stowey - Solar Farm', 'Regener8 Power', 'solar_ground', 49.9, 'awaiting_construction', 'Somerset', 'South West', 'BS39 4DN', 58.2, 359671.0, 160455.0),
    ('8393', 'Rag Lane  Solar Farm', 'BayWa r.e. UK Limited', 'solar_ground', 49.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL12 8LD', NULL, 370675.0, 188289.0),
    ('8505', 'Fernbrook - Solar farm & Battery storage', 'Low Carbon UK Solar Investment Company Limited', 'solar_ground', 49.9, 'awaiting_construction', 'Dorset', 'South West', 'SP8 5JG', 39.1, 382223.0, 125442.0),
    ('8843', 'Moreton Lane - Solar Farm & Battery Storage', 'JBM Solar Projects 7 Limited', 'solar_ground', 49.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL2 7PN', 116.0, 378521.0, 210762.0),
    ('8889', 'Hill Court, Tranton Lane Hill - Solar Farm', 'Longlands Solar Farm Limited', 'solar_ground', 49.9, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL13 9ED', 72.5, 363605.0, 196251.0),
    ('17616', 'Etex Building Performance, Redland Avenue - Solar Panels', 'PROMAT UK/Etex Building Performance Limited', 'solar_rooftop', 6.17, 'awaiting_construction', 'Somerset', 'South West', 'BS20 0FB', NULL, 350746.0, 176985.0),
    ('17613', 'Etex Building Performance, Redland Avenue - Solar PV panels', 'PROMAT UK/Etex Building Performance Limited', 'solar_rooftop', 5.9, 'awaiting_construction', 'Somerset', 'South West', 'BS20 0FB', NULL, 350746.0, 176985.0),
    ('16178', 'Unilever UK, Corinium Avenue - Solar Panels', 'Unilever UK', 'solar_rooftop', 3.5, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL4 3BW', NULL, 386206.0, 218906.0),
    ('12267', 'Amazon, Symmetry Park - Solar Panels', 'Push Energy', 'solar_rooftop', 3.26, 'awaiting_construction', 'Wiltshire', 'South West', 'SN3 4DB', NULL, 419586.0, 186730.0),
    ('16014', 'Airbus UK Industrial Complex - Solar panels', 'Custom Solar Limited', 'solar_rooftop', 3.14, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS34 7PA', NULL, 360015.0, 179529.0),
    ('14415', 'Smart Systems Limited, Arnolds Way - Solar Panels', 'Smart Systems Limited', 'solar_rooftop', 2.93, 'under_construction', 'Somerset', 'South West', 'BS49 4QN', 1.38, 341752.0, 166241.0),
    ('5653', 'B&Q Swindon DC', 'Kingfisher Scottish Limited Partnership', 'solar_rooftop', 2.5, 'operational', 'Wiltshire', 'South West', 'SN3 4TZ', NULL, 417904.0, 189004.0),
    ('19056', 'The Range Distribution Centre, Severn Beach - Solar panels', 'InRange Limited', 'solar_rooftop', 2.4, 'awaiting_construction', 'Gloucestershire', 'South West', 'BS35 4EL', NULL, 355221.0, 181965.0),
    ('15782', 'Orbital Shopping Park, North Swindon District Centre - Solar panels', 'Orbital Retail Park Swindon Limited', 'solar_rooftop', 2.0, 'awaiting_construction', 'Wiltshire', 'South West', 'SN25 4AN', NULL, 413361.0, 188758.0),
    ('15022', 'Unit O, Penzance Drive - Solar Panels', 'Ortus Energy', 'solar_rooftop', 1.96, 'awaiting_construction', 'Wiltshire', 'South West', 'SN5 7JF', 0.95, 413343.0, 184267.0),
    ('6043', 'Rolls Royce Filton Campus Building 185', 'Innogy (previously BELECTRIC Solar)', 'solar_rooftop', 1.8, 'operational', 'Avon', 'South West', 'BS34 6QA', NULL, 360460.0, 180792.0),
    ('5312', 'Amcor Flexibles', 'Langley Eco', 'solar_rooftop', 1.7, 'operational', 'Gloucestershire', 'South West', 'BS34 6PT', NULL, 363561.0, 180524.0),
    ('11837', 'Parsonage Way - Solar Panels', 'Wavin Plastic Limited', 'solar_rooftop', 1.6, 'awaiting_construction', 'Wiltshire', 'South West', 'SN15 5PN', 2.26, 392674.0, 174686.0),
    ('16257', 'Delphi Diesel Systems, Brunel Way -  Solar Panels', 'Phinia Delphi UK Limited', 'solar_rooftop', 1.6, 'awaiting_construction', 'Gloucestershire', 'South West', 'GL10 3SX', NULL, 379346.0, 205911.0),
    ('19181', 'VPK Wellington, Chelston Business Park -  Solar Panel', 'SNRG', 'solar_rooftop', 1.6, 'awaiting_construction', 'Somerset', 'South West', 'TA21 9JG', NULL, 315609.0, 121420.0),
    ('5079', 'Newton Margate', 'Tulip Meats', 'solar_rooftop', 1.5, 'operational', 'Cornwall', 'South West', 'PL31 1HF', NULL, 208517.0, 66931.0),
    ('4033', 'Fullabrook Down Wind Farm', 'Devon Wind Power Ltd', 'wind', 66.0, 'operational', 'Devon', 'South West', NULL, NULL, 253055.0, 141846.0),
    ('15407', 'Bears Down Wind Farm', 'Clean Earth Energy Limited', 'wind', 22.5, 'submitted', 'Cornwall', 'South West', 'PL27 7TA', NULL, 189147.0, 70197.0),
    ('9017', 'Cold Northcott Windfarm Repowering', 'RMA Environmental Limited', 'wind', 22.0, 'submitted', 'Cornwall', 'South West', 'PL15', NULL, 231780.0, 83565.0),
    ('3976', 'Carland Cross Wind Farm Repowering', 'Scottish Power Renewables', 'wind', 20.0, 'operational', 'Cornwall', 'South West', NULL, NULL, 184500.0, 54500.0),
    ('4057', 'Batsworthy Cross', 'Blackrock Real Assets', 'wind', 18.0, 'operational', 'Devon', 'South West', NULL, NULL, 281500.0, 120500.0),
    ('4266', 'Den Brook', 'Aviva', 'wind', 18.0, 'operational', 'Devon', 'South West', NULL, NULL, 268500.0, 99500.0),
    ('3061', 'Goonhilly Downs Wind Farm Repower', 'REG Windpower (previously  Cornwall Light & Power)', 'wind', 12.0, 'operational', 'Cornwall', 'South West', NULL, NULL, 171000.0, 21600.0),
    ('3077', 'Carn Vean', 'Unknown', 'wind', 10.0, 'operational', 'Cornwall', 'South West', 'TR3 7BY', NULL, 172528.0, 35961.0),
    ('4604', 'St. Breock Re-Power', 'REG & Blackrock', 'wind', 10.0, 'operational', 'Cornwall', 'South West', NULL, NULL, 200000.0, 70000.0),
    ('4651', 'Denzell Downs Wind Farm', 'REG Windpower / BlackRock', 'wind', 10.0, 'operational', 'Cornwall', 'South West', 'TR8 4HG', NULL, 189923.0, 67094.0),
    ('3392', 'Bears Down Wind Farm', 'Natural Power', 'wind', 9.8, 'operational', 'Cornwall', 'South West', NULL, NULL, 190360.0, 67560.0),
    ('3019', 'Delabole (Repowering)', 'Good Energy Generation', 'wind', 9.2, 'operational', 'Cornwall', 'South West', NULL, NULL, 208800.0, 85500.0),
    ('4333', 'Alaska Wind Farm', 'Alaska (formerly Purbeck Wind Farm LLP c/o Infinergy)', 'wind', 9.2, 'awaiting_construction', 'Dorset', 'South West', 'BH20 6BA', NULL, 387544.0, 87398.0),
    ('4624', 'Galsworthy Wind Park', 'Ecotricity', 'wind', 9.2, 'operational', 'Devon', 'South West', NULL, NULL, 240435.0, 115705.0),
    ('4159', 'Avonmouth Port - extension', 'Bristol Port Company', 'wind', 9.0, 'operational', 'Avon', 'South West', 'BS11 9DQ', NULL, 351593.0, 178451.0),
    ('3664', 'Avonmouth Wind Power', 'Wessex Water Engineering Services', 'wind', 8.2, 'operational', 'Avon', 'South West', NULL, NULL, 353358.0, 179393.0)
) AS v(ref_id, title, operator, technology, capacity_mw, status, county, region,
       postcode, site_area_hectares, easting, northing);

UPDATE projects
SET site_area_hectares = round((capacity_mw * 0.8)::numeric, 1)
WHERE technology = 'solar_ground' AND site_area_hectares IS NULL AND capacity_mw IS NOT NULL;

UPDATE projects
SET footprint = ST_Buffer(geom::geography, sqrt(site_area_hectares * 10000 / pi()))::geometry
WHERE technology = 'solar_ground' AND site_area_hectares IS NOT NULL;
