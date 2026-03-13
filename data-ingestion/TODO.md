# TODO — DuPage County Gap Fixes

## P0 — Critical

- [x] Parse & store permitted/conditional/special uses from zoning ordinances
- [x] Add `permitted_uses` to `get_zoning_info` tool response

## P1 — High

- [x] Ingest zoning geometry layer from DuPage ArcGIS
- [ ] Add more filters to `filter_parcels` (bldg_sqft, township, zoning)

## P2 — Medium

- [ ] Incremental/delta ingestion (track last OID/timestamp per layer)
- [ ] README with architecture decisions and tradeoffs

## P3 — Nice to Have

- [ ] Checkpoint/resume for pipeline
