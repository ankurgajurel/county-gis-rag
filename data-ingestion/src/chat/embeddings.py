"""Generate text chunks from structured data and embed them into pgvector."""

import logging

from openai import AsyncOpenAI
from sqlalchemy import select, delete

from src.config import settings
from src.db.engine import async_session
from src.db.models import (
    County,
    DataSource,
    DiscoveredLayer,
    DocumentChunk,
    Municipality,
    ZoningDistrict,
)

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 50

FIELD_ALIASES = {
    "PIN": "parcel identification number",
    "PROPSTNUM": "property street number",
    "PROPSTDIR": "property street direction",
    "PROPSTNAME": "property street name",
    "PROPAPT": "property apartment/unit",
    "PROPCITY": "property city",
    "PROPZIP": "property zip code",
    "PROPADDRL1": "property address line 1",
    "PROPADDRL2": "property address line 2",
    "MAJOR_PROPERTY_OWNER": "major property owner name",
    "ACREAGE": "parcel acreage",
    "ACRE_SOURCE": "acreage data source",
    "OBJECTID": "internal object ID",
    "BOUNDARY": "boundary type",
    "BFE": "base flood elevation",
    "CNTR_ELEV": "contour elevation",
    "SHD_CODE": "watershed code",
    "SHD_ACRES": "watershed area in acres",
    "SHD_LOC": "watershed location",
    "RIVERBASIN": "river basin name",
    "TRIBUTARY": "tributary name",
    "CATCHMENT": "catchment area name",
    "TOWNSHIP": "township name",
    "SECTION_": "section number",
    "COUNTY": "county name",
    "DESIGNATION": "benchmark designation",
    "ELEV_US": "elevation (US survey feet)",
}


async def build_and_embed():
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    chunks = []
    chunks.extend(await _zoning_chunks())
    chunks.extend(await _layer_chunks())

    logger.info("Generated %d text chunks", len(chunks))

    async with async_session() as db:
        await db.execute(delete(DocumentChunk))
        await db.commit()

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]

        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )

        async with async_session() as db:
            for chunk, emb_data in zip(batch, response.data):
                db.add(DocumentChunk(
                    source_type=chunk["source_type"],
                    source_id=chunk["source_id"],
                    chunk_text=chunk["chunk_text"],
                    embedding=emb_data.embedding,
                    metadata_=chunk.get("metadata"),
                ))
            await db.commit()

        logger.info("Embedded batch %d-%d", i, i + len(batch))

    logger.info("Done. %d chunks embedded.", len(chunks))


async def _zoning_chunks() -> list[dict]:
    chunks = []

    async with async_session() as db:
        result = await db.execute(
            select(ZoningDistrict, Municipality.name.label("muni_name"))
            .join(Municipality, ZoningDistrict.municipality_id == Municipality.id)
        )
        rows = result.all()

    for zd, muni_name in rows:
        parts = [f"{muni_name} zoning district {zd.code} — {zd.name}."]

        if zd.category:
            parts.append(f"Category: {zd.category}.")

        if zd.regulations:
            reg_parts = []
            mapping = {
                "min_lot_size_sqft": ("Minimum lot size", "sqft"),
                "max_height_ft": ("Maximum building height", "ft"),
                "front_setback_ft": ("Front setback", "ft"),
                "side_setback_ft": ("Side setback", "ft"),
                "rear_setback_ft": ("Rear setback", "ft"),
                "floor_area_ratio": ("Floor area ratio (FAR)", ""),
            }
            for key, (label, unit) in mapping.items():
                val = zd.regulations.get(key)
                if val is not None:
                    suffix = f" {unit}" if unit else ""
                    reg_parts.append(f"{label}: {val:,}{suffix}" if isinstance(val, int) else f"{label}: {val}{suffix}")
            if reg_parts:
                parts.append("Regulations: " + ". ".join(reg_parts) + ".")

        if zd.raw_text:
            parts.append(f"Ordinance text: {zd.raw_text[:2000]}")

        chunks.append({
            "source_type": "zoning",
            "source_id": zd.id,
            "chunk_text": " ".join(parts),
            "metadata": {"municipality": muni_name, "code": zd.code, "category": zd.category},
        })

    return chunks


async def _layer_chunks() -> list[dict]:
    chunks = []

    async with async_session() as db:
        result = await db.execute(
            select(DiscoveredLayer, County.name.label("county_name"))
            .join(DataSource, DiscoveredLayer.data_source_id == DataSource.id)
            .join(County, DataSource.county_id == County.id)
            .where(DiscoveredLayer.geometry_type.isnot(None))
        )
        rows = result.all()

    for layer, county_name in rows:
        parts = [f"{layer.layer_name} — {layer.geometry_type} layer in {county_name} County."]

        if layer.feature_count:
            parts.append(f"Contains {layer.feature_count:,} features.")

        parts.append(f"Service: {layer.service_name}/{layer.service_type}.")

        if layer.field_schema:
            field_descs = []
            for f in layer.field_schema:
                name = f.get("name", "")
                if name in ("OBJECTID", "Shape", "Shape.area", "Shape.len",
                            "Shape.STArea()", "Shape.STLength()", "Shape__Length"):
                    continue
                alias = FIELD_ALIASES.get(name, f.get("alias", name))
                field_descs.append(f"{name} ({alias})")

            if field_descs:
                parts.append("Fields: " + ", ".join(field_descs[:20]) + ".")

        layer_name_lower = layer.layer_name.lower()
        tags = []
        if "flood" in layer_name_lower:
            tags.append("flooding")
        if "parcel" in layer_name_lower or "assessment" in layer_name_lower:
            tags.append("parcels")
        if "zoning" in layer_name_lower:
            tags.append("zoning")
        if "school" in layer_name_lower:
            tags.append("school districts")
        if "watershed" in layer_name_lower or "catchment" in layer_name_lower:
            tags.append("hydrology")
        if "contour" in layer_name_lower or "elevation" in layer_name_lower:
            tags.append("elevation/topography")
        if "address" in layer_name_lower:
            tags.append("addresses")
        if "road" in layer_name_lower or "street" in layer_name_lower:
            tags.append("transportation")
        if "boundary" in layer_name_lower or "municipal" in layer_name_lower:
            tags.append("boundaries")
        if "tax" in layer_name_lower or "tif" in layer_name_lower:
            tags.append("taxation")
        if tags:
            parts.append("Related topics: " + ", ".join(tags) + ".")

        chunks.append({
            "source_type": "layer",
            "source_id": layer.id,
            "chunk_text": " ".join(parts),
            "metadata": {"county": county_name, "layer_name": layer.layer_name},
        })

    return chunks
