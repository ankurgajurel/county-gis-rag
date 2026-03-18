"""Tool functions that query PostGIS. Each returns a dict suitable for LLM consumption."""

import json as _json

from openai import AsyncOpenAI
from sqlalchemy import select, func, text, cast, String
from geoalchemy2.functions import ST_AsText, ST_DWithin, ST_Intersects, ST_Transform

from src.config import settings
from src.db.engine import async_session
from src.db.models import (
    County,
    DiscoveredLayer,
    DocumentChunk,
    GISFeature,
    Municipality,
    Parcel,
    ZoningDistrict,
    ZoningGeometry,
)

MAX_RESULTS = 20
MAX_GEOJSON_FEATURES = 50


async def lookup_parcel(
    pin: str | None = None,
    address: str | None = None,
    county: str | None = None,
    include_geometry: bool = True,
) -> dict:
    if not pin and not address:
        return {"error": "Provide either pin or address"}

    async with async_session() as db:
        columns = [
            Parcel.pin,
            Parcel.prop_address,
            Parcel.prop_city,
            Parcel.prop_zip,
            Parcel.owner_name,
            Parcel.property_class,
            Parcel.class_description,
            Parcel.assessed_value_total,
            Parcel.assessed_value_land,
            Parcel.assessed_value_bldg,
            Parcel.tax_amount,
            Parcel.acreage,
            Parcel.land_sqft,
            Parcel.bldg_sqft,
            Parcel.municipality,
            Parcel.township,
            Parcel.legal_description,
            County.name.label("county_name"),
        ]
        if include_geometry:
            columns.append(func.ST_AsGeoJSON(Parcel.geom).label("geojson"))

        q = select(*columns).join(County, Parcel.county_id == County.id)

        if pin:
            q = q.where(Parcel.pin == pin)
        if address:
            q = q.where(Parcel.prop_address.ilike(f"%{address}%"))
        if county:
            q = q.where(County.name.ilike(f"%{county}%"))

        q = q.limit(MAX_RESULTS)
        result = await db.execute(q)
        rows = result.mappings().all()

    if not rows:
        return {"results": [], "message": "No parcels found"}

    results = []
    features = []
    for r in rows:
        entry = {k: v for k, v in dict(r).items() if k != "geojson"}
        results.append(entry)
        if include_geometry and r.get("geojson"):
            geom = _json.loads(r["geojson"])
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "pin": r["pin"],
                    "source": "parcel",
                    "prop_address": r.get("prop_address"),
                    "municipality": r.get("municipality"),
                    "assessed_value_total": r.get("assessed_value_total"),
                    "county_name": r.get("county_name"),
                },
            })

    out = {
        "results": results,
        "count": len(results),
        "truncated": len(results) == MAX_RESULTS,
    }

    if include_geometry and features:
        out["geojson"] = _build_feature_collection(features)

    return out


async def filter_parcels(
    county: str | None = None,
    municipality: str | None = None,
    property_class: str | None = None,
    min_assessed_value: int | None = None,
    max_assessed_value: int | None = None,
    min_land_sqft: float | None = None,
    max_land_sqft: float | None = None,
    limit: int = 20,
) -> dict:
    limit = min(limit, 50)

    async with async_session() as db:
        q = select(
            Parcel.pin,
            Parcel.prop_address,
            Parcel.prop_city,
            Parcel.municipality,
            Parcel.property_class,
            Parcel.class_description,
            Parcel.assessed_value_total,
            Parcel.land_sqft,
            Parcel.acreage,
            County.name.label("county_name"),
        ).join(County, Parcel.county_id == County.id)

        if county:
            q = q.where(County.name.ilike(f"%{county}%"))
        if municipality:
            q = q.where(Parcel.municipality.ilike(f"%{municipality}%"))
        if property_class:
            q = q.where(Parcel.property_class == property_class)
        if min_assessed_value is not None:
            q = q.where(Parcel.assessed_value_total >= min_assessed_value)
        if max_assessed_value is not None:
            q = q.where(Parcel.assessed_value_total <= max_assessed_value)
        if min_land_sqft is not None:
            q = q.where(Parcel.land_sqft >= min_land_sqft)
        if max_land_sqft is not None:
            q = q.where(Parcel.land_sqft <= max_land_sqft)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(count_q)).scalar()

        q = q.limit(limit)
        result = await db.execute(q)
        rows = result.mappings().all()

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
        "total_matching": total,
        "truncated": total > limit,
    }


async def spatial_query(
    lat: float,
    lon: float,
    radius_ft: float = 100,
    layer_name: str | None = None,
    county: str | None = None,
) -> dict:
    radius_m = radius_ft * 0.3048

    async with async_session() as db:
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        point_geog = cast(point, text("geography"))

        q = select(
            GISFeature.layer_name,
            GISFeature.feature_id,
            GISFeature.attributes,
        ).where(
            ST_DWithin(
                cast(GISFeature.geom, text("geography")),
                point_geog,
                radius_m,
            )
        )

        if layer_name:
            q = q.where(GISFeature.layer_name.ilike(f"%{layer_name}%"))
        if county:
            q = q.join(County, GISFeature.county_id == County.id).where(
                County.name.ilike(f"%{county}%")
            )

        q = q.limit(MAX_RESULTS)
        result = await db.execute(q)
        rows = result.mappings().all()

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
        "truncated": len(rows) == MAX_RESULTS,
    }


async def parcel_spatial_query(
    pin: str,
    layer_name: str | None = None,
) -> dict:
    async with async_session() as db:
        parcel = (
            await db.execute(select(Parcel).where(Parcel.pin == pin))
        ).scalar_one_or_none()

        if not parcel:
            return {"error": f"Parcel {pin} not found"}
        if parcel.geom is None:
            return {"error": f"Parcel {pin} has no geometry"}

        q = select(
            GISFeature.layer_name,
            GISFeature.feature_id,
            GISFeature.attributes,
        ).where(
            ST_Intersects(GISFeature.geom, parcel.geom),
            GISFeature.county_id == parcel.county_id,
        )

        if layer_name:
            q = q.where(GISFeature.layer_name.ilike(f"%{layer_name}%"))

        q = q.limit(MAX_RESULTS)
        result = await db.execute(q)
        rows = result.mappings().all()

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
        "truncated": len(rows) == MAX_RESULTS,
    }


async def get_zoning_info(
    municipality: str | None = None,
    code: str | None = None,
    category: str | None = None,
) -> dict:
    async with async_session() as db:
        q = select(
            ZoningDistrict.code,
            ZoningDistrict.name,
            ZoningDistrict.category,
            ZoningDistrict.description,
            ZoningDistrict.regulations,
            ZoningDistrict.source_url,
            Municipality.name.label("municipality_name"),
        ).join(Municipality, ZoningDistrict.municipality_id == Municipality.id)

        if municipality:
            q = q.where(Municipality.name.ilike(f"%{municipality}%"))
        if code:
            q = q.where(ZoningDistrict.code.ilike(f"%{code}%"))
        if category:
            q = q.where(ZoningDistrict.category == category)

        q = q.limit(MAX_RESULTS)
        result = await db.execute(q)
        rows = result.mappings().all()

    results = []
    for r in rows:
        entry = dict(r)
        regs = entry.get("regulations") or {}
        entry["permitted_uses"] = regs.get("permitted_uses", [])
        entry["conditional_uses"] = regs.get("conditional_uses", [])
        entry["special_uses"] = regs.get("special_uses", [])
        results.append(entry)

    return {
        "results": results,
        "count": len(results),
    }


async def get_parcel_zoning(
    pin: str | None = None,
    address: str | None = None,
    county: str | None = None,
) -> dict:
    """Find zoning designation for a parcel using spatial intersection with zoning geometries."""
    if not pin and not address:
        return {"error": "Provide either pin or address"}

    async with async_session() as db:
        q = select(Parcel).join(County, Parcel.county_id == County.id)
        if pin:
            q = q.where(Parcel.pin == pin)
        if address:
            q = q.where(Parcel.prop_address.ilike(f"%{address}%"))
        if county:
            q = q.where(County.name.ilike(f"%{county}%"))

        q = q.limit(1)
        parcel = (await db.execute(q)).scalar_one_or_none()

        if not parcel:
            return {"error": "Parcel not found"}
        if parcel.geom is None:
            return {"error": f"Parcel {parcel.pin} has no geometry"}

        zq = select(
            ZoningGeometry.zone_code,
            ZoningGeometry.attributes,
        ).where(
            ST_Intersects(ZoningGeometry.geom, parcel.geom),
            ZoningGeometry.county_id == parcel.county_id,
        )

        result = await db.execute(zq)
        zones = result.mappings().all()

        # Also look up zoning district details for matched codes
        zone_details = []
        for z in zones:
            detail = {"zone_code": z["zone_code"], "attributes": z["attributes"]}

            district = (await db.execute(
                select(
                    ZoningDistrict.code,
                    ZoningDistrict.name,
                    ZoningDistrict.category,
                    ZoningDistrict.regulations,
                    Municipality.name.label("municipality_name"),
                )
                .join(Municipality, ZoningDistrict.municipality_id == Municipality.id)
                .where(ZoningDistrict.code.ilike(f"%{z['zone_code']}%"))
                .limit(1)
            )).mappings().first()

            if district:
                d = dict(district)
                regs = d.get("regulations") or {}
                detail["district"] = d
                detail["permitted_uses"] = regs.get("permitted_uses", [])
                detail["conditional_uses"] = regs.get("conditional_uses", [])
                detail["special_uses"] = regs.get("special_uses", [])

            zone_details.append(detail)

    return {
        "parcel_pin": parcel.pin,
        "parcel_address": parcel.prop_address,
        "zoning_results": zone_details,
        "count": len(zone_details),
    }


async def list_available_layers(county: str | None = None) -> dict:
    from src.db.models import DataSource

    async with async_session() as db:
        q = (
            select(
                DiscoveredLayer.layer_name,
                DiscoveredLayer.service_name,
                DiscoveredLayer.geometry_type,
                DiscoveredLayer.feature_count,
                DiscoveredLayer.service_type,
                County.name.label("county_name"),
            )
            .join(DataSource, DiscoveredLayer.data_source_id == DataSource.id)
            .join(County, DataSource.county_id == County.id)
        )

        if county:
            q = q.where(County.name.ilike(f"%{county}%"))

        q = q.where(DiscoveredLayer.geometry_type.isnot(None))
        q = q.order_by(DiscoveredLayer.layer_name)
        q = q.limit(100)

        result = await db.execute(q)
        rows = result.mappings().all()

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
    }


async def query_gis_layer(
    layer_name: str,
    county: str | None = None,
    attribute_filter: dict | None = None,
    limit: int = 20,
) -> dict:
    limit = min(limit, 50)

    async with async_session() as db:
        q = select(
            GISFeature.layer_name,
            GISFeature.feature_id,
            GISFeature.attributes,
            County.name.label("county_name"),
        ).join(County, GISFeature.county_id == County.id)

        q = q.where(GISFeature.layer_name.ilike(f"%{layer_name}%"))

        if county:
            q = q.where(County.name.ilike(f"%{county}%"))
        if attribute_filter:
            q = q.where(GISFeature.attributes.contains(attribute_filter))

        q = q.limit(limit)
        result = await db.execute(q)
        rows = result.mappings().all()

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
        "truncated": len(rows) == limit,
    }


async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    query_embedding = response.data[0].embedding

    async with async_session() as db:
        result = await db.execute(
            select(
                DocumentChunk.chunk_text,
                DocumentChunk.source_type,
                DocumentChunk.metadata_,
                DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .order_by("distance")
            .limit(top_k)
        )
        rows = result.all()

    return {
        "results": [
            {
                "text": row[0],
                "source_type": row[1],
                "metadata": row[2],
                "relevance_score": round(1 - row[3], 3),
            }
            for row in rows
        ],
        "count": len(rows),
    }


def _build_feature_collection(features: list[dict]) -> dict:
    """Build a GeoJSON FeatureCollection with bounding box."""
    coords: list[tuple[float, float]] = []
    for f in features:
        geom = f.get("geometry")
        if not geom:
            continue
        _extract_coords(geom.get("coordinates", []), coords)

    bbox = None
    if coords:
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bbox = [min(lons), min(lats), max(lons), max(lats)]

    fc: dict = {"type": "FeatureCollection", "features": features}
    if bbox:
        fc["bbox"] = bbox
    return fc


def _extract_coords(coords, out: list[tuple[float, float]]):
    """Recursively extract (lon, lat) pairs from nested coordinate arrays."""
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        out.append((coords[0], coords[1]))
    elif isinstance(coords[0], list):
        for c in coords:
            _extract_coords(c, out)


async def get_geometry(
    pin: str | None = None,
    layer_name: str | None = None,
    feature_ids: list[str] | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_ft: float = 500,
) -> dict:
    """Return a GeoJSON FeatureCollection for map visualization."""
    features: list[dict] = []

    async with async_session() as db:
        # Mode 1: By parcel PIN — return parcel + intersecting GIS features
        if pin:
            parcel_q = select(
                Parcel.pin,
                Parcel.prop_address,
                Parcel.municipality,
                Parcel.assessed_value_total,
                Parcel.county_id,
                Parcel.geom,
                func.ST_AsGeoJSON(Parcel.geom).label("geojson"),
            ).where(Parcel.pin == pin)

            parcel_row = (await db.execute(parcel_q)).mappings().first()
            if not parcel_row:
                return {"error": f"Parcel {pin} not found"}

            if parcel_row["geojson"]:
                features.append({
                    "type": "Feature",
                    "geometry": _json.loads(parcel_row["geojson"]),
                    "properties": {
                        "pin": parcel_row["pin"],
                        "source": "parcel",
                        "prop_address": parcel_row.get("prop_address"),
                        "municipality": parcel_row.get("municipality"),
                        "assessed_value_total": parcel_row.get("assessed_value_total"),
                    },
                })

                # Find intersecting GIS features
                gis_q = select(
                    GISFeature.layer_name,
                    GISFeature.feature_id,
                    GISFeature.attributes,
                    func.ST_AsGeoJSON(GISFeature.geom).label("geojson"),
                ).where(
                    ST_Intersects(GISFeature.geom, parcel_row["geom"]),
                    GISFeature.county_id == parcel_row["county_id"],
                ).limit(MAX_GEOJSON_FEATURES - 1)

                gis_rows = (await db.execute(gis_q)).mappings().all()
                for r in gis_rows:
                    if r["geojson"]:
                        features.append({
                            "type": "Feature",
                            "geometry": _json.loads(r["geojson"]),
                            "properties": {
                                "source": "gis_feature",
                                "layer_name": r["layer_name"],
                                "feature_id": r["feature_id"],
                                **(r["attributes"] or {}),
                            },
                        })

        # Mode 2: By layer name + optional feature IDs
        elif layer_name:
            q = select(
                GISFeature.layer_name,
                GISFeature.feature_id,
                GISFeature.attributes,
                func.ST_AsGeoJSON(GISFeature.geom).label("geojson"),
            ).where(GISFeature.layer_name.ilike(f"%{layer_name}%"))

            if feature_ids:
                q = q.where(GISFeature.feature_id.in_(feature_ids))

            q = q.limit(MAX_GEOJSON_FEATURES)
            rows = (await db.execute(q)).mappings().all()

            for r in rows:
                if r["geojson"]:
                    features.append({
                        "type": "Feature",
                        "geometry": _json.loads(r["geojson"]),
                        "properties": {
                            "source": "gis_feature",
                            "layer_name": r["layer_name"],
                            "feature_id": r["feature_id"],
                            **(r["attributes"] or {}),
                        },
                    })

        # Mode 3: By lat/lon radius
        elif lat is not None and lon is not None:
            radius_m = radius_ft * 0.3048
            point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
            point_geog = cast(point, text("geography"))

            # Parcels in radius
            p_q = select(
                Parcel.pin,
                Parcel.prop_address,
                Parcel.municipality,
                Parcel.assessed_value_total,
                func.ST_AsGeoJSON(Parcel.geom).label("geojson"),
            ).where(
                ST_DWithin(cast(Parcel.geom, text("geography")), point_geog, radius_m)
            ).limit(MAX_GEOJSON_FEATURES // 2)

            for r in (await db.execute(p_q)).mappings().all():
                if r["geojson"]:
                    features.append({
                        "type": "Feature",
                        "geometry": _json.loads(r["geojson"]),
                        "properties": {
                            "pin": r["pin"],
                            "source": "parcel",
                            "prop_address": r.get("prop_address"),
                            "municipality": r.get("municipality"),
                            "assessed_value_total": r.get("assessed_value_total"),
                        },
                    })

            # GIS features in radius
            g_q = select(
                GISFeature.layer_name,
                GISFeature.feature_id,
                GISFeature.attributes,
                func.ST_AsGeoJSON(GISFeature.geom).label("geojson"),
            ).where(
                ST_DWithin(cast(GISFeature.geom, text("geography")), point_geog, radius_m)
            ).limit(MAX_GEOJSON_FEATURES // 2)

            for r in (await db.execute(g_q)).mappings().all():
                if r["geojson"]:
                    features.append({
                        "type": "Feature",
                        "geometry": _json.loads(r["geojson"]),
                        "properties": {
                            "source": "gis_feature",
                            "layer_name": r["layer_name"],
                            "feature_id": r["feature_id"],
                            **(r["attributes"] or {}),
                        },
                    })

        else:
            return {"error": "Provide pin, layer_name, or lat/lon coordinates"}

    if not features:
        return {"type": "FeatureCollection", "features": []}

    return _build_feature_collection(features)


TOOL_REGISTRY = {
    "lookup_parcel": lookup_parcel,
    "filter_parcels": filter_parcels,
    "spatial_query": spatial_query,
    "parcel_spatial_query": parcel_spatial_query,
    "get_zoning_info": get_zoning_info,
    "get_parcel_zoning": get_parcel_zoning,
    "list_available_layers": list_available_layers,
    "query_gis_layer": query_gis_layer,
    "search_knowledge_base": search_knowledge_base,
    "get_geometry": get_geometry,
}
