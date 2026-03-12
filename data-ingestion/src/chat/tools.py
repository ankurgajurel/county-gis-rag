"""Tool functions that query PostGIS. Each returns a dict suitable for LLM consumption."""

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
)

MAX_RESULTS = 20


async def lookup_parcel(
    pin: str | None = None,
    address: str | None = None,
    county: str | None = None,
) -> dict:
    if not pin and not address:
        return {"error": "Provide either pin or address"}

    async with async_session() as db:
        q = select(
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
        ).join(County, Parcel.county_id == County.id)

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

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
        "truncated": len(rows) == MAX_RESULTS,
    }


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

    return {
        "results": [dict(r) for r in rows],
        "count": len(rows),
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


TOOL_REGISTRY = {
    "lookup_parcel": lookup_parcel,
    "filter_parcels": filter_parcels,
    "spatial_query": spatial_query,
    "parcel_spatial_query": parcel_spatial_query,
    "get_zoning_info": get_zoning_info,
    "list_available_layers": list_available_layers,
    "query_gis_layer": query_gis_layer,
    "search_knowledge_base": search_knowledge_base,
}
