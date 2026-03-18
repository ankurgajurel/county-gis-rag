"""Build the system prompt dynamically from the database."""

from sqlalchemy import select, func

from src.db.engine import async_session
from src.db.models import (
    County,
    DataSource,
    DiscoveredLayer,
    Municipality,
    Parcel,
    ZoningDistrict,
)


async def build_system_prompt() -> str:
    context = await _gather_context()

    return f"""You are a county GIS data assistant. You help users query parcel records, zoning information, and geographic features across counties.

## Core behavior

- NEVER ask clarifying questions. Just do the work. If the user's question can be answered by calling tools, call them immediately and give a complete answer.
- If a question is ambiguous, pick the most likely interpretation and answer it. Mention your assumption briefly if needed.
- Always include map visualization when the answer involves locations, areas, parcels, or boundaries. Users always want to see things on the map — don't ask.
- Be direct and concise. Lead with the answer, not the process.
- When listing geographic entities (municipalities, layers, zones), always fetch and show their boundaries on the map.

## Available data

{context["counties_section"]}

{context["layers_section"]}

{context["zoning_section"]}

## Parcel fields

Each parcel record has: PIN (unique identifier), address, city, zip, owner name, property class, class description, assessed values (land, building, total), tax code, tax rate, tax amount, acreage, land sqft, building sqft, building age, lot dimensions, municipality, township, legal description, and geometry.

## How to answer questions

- For address/PIN lookups: use lookup_parcel
- For "what's the zoning at X": first lookup_parcel to get the PIN, then use parcel_spatial_query to find intersecting zoning layers, and get_zoning_info for district details
- For filtering parcels by criteria: use filter_parcels
- For "what layers/data do we have": use list_available_layers
- For "what's near [address]" or "is [address] in a flood zone": use geocode_and_query
- Prefer geocode_and_query over spatial_query when the user gives an address instead of coordinates
- For spatial questions with coordinates ("what's near X", "is this in a flood zone"): use spatial_query or parcel_spatial_query
- For zoning regulations (setbacks, height limits): use get_zoning_info
- For querying specific GIS layers: use query_gis_layer
- For understanding zoning regulations, finding the right GIS layer for a concept, or looking up field meanings: use search_knowledge_base. This searches embedded descriptions of zoning districts and GIS layers.
- For "what municipalities" or "list municipalities": use query_gis_layer on the Municipality layer and get_geometry to show boundaries

## Map visualization

ALWAYS call `get_geometry` after your data lookup to provide map visualization. The frontend will automatically render any GeoJSON on an interactive map. Do not skip this step — users expect to see results on the map.

Call patterns:
- After lookup_parcel: call get_geometry with the PIN to show the parcel on the map
- After spatial_query: call get_geometry with the same lat/lon to show features on the map
- After get_parcel_zoning: call get_geometry with the PIN to show parcel + zoning boundaries
- After query_gis_layer: call get_geometry for the relevant layer to show boundaries
- When listing municipalities, zones, or areas: always include get_geometry to show their boundaries
- When the user says "show me" or "where is": always include get_geometry

When answering, be specific with numbers and cite the data. If results are truncated, mention that more results exist."""


async def _gather_context() -> dict:
    async with async_session() as db:
        counties = (await db.execute(
            select(County.name, County.fips_code)
        )).mappings().all()

        parcel_counts = (await db.execute(
            select(County.name, func.count(Parcel.id))
            .join(Parcel, Parcel.county_id == County.id)
            .group_by(County.name)
        )).all()

        layer_summary = (await db.execute(
            select(
                County.name,
                DiscoveredLayer.layer_name,
                DiscoveredLayer.geometry_type,
                DiscoveredLayer.feature_count,
            )
            .join(DataSource, DiscoveredLayer.data_source_id == DataSource.id)
            .join(County, DataSource.county_id == County.id)
            .where(DiscoveredLayer.geometry_type.isnot(None))
            .order_by(County.name, DiscoveredLayer.layer_name)
        )).all()

        zoning = (await db.execute(
            select(
                Municipality.name,
                ZoningDistrict.code,
                ZoningDistrict.name.label("district_name"),
                ZoningDistrict.category,
            )
            .join(ZoningDistrict, ZoningDistrict.municipality_id == Municipality.id)
            .order_by(Municipality.name, ZoningDistrict.code)
        )).all()

    counties_lines = ["### Counties"]
    for c in counties:
        count = next((pc[1] for pc in parcel_counts if pc[0] == c["name"]), 0)
        counties_lines.append(f"- **{c['name']}** (FIPS {c['fips_code']}): {count:,} parcels")

    layers_lines = ["### GIS layers"]
    current_county = None
    for row in layer_summary:
        if row[0] != current_county:
            current_county = row[0]
            layers_lines.append(f"\n**{current_county}:**")
        count_str = f" ({row[3]:,} features)" if row[3] else ""
        layers_lines.append(f"- {row[1]} [{row[2]}]{count_str}")

    zoning_lines = ["### Zoning districts"]
    current_muni = None
    for row in zoning:
        if row[0] != current_muni:
            current_muni = row[0]
            zoning_lines.append(f"\n**{current_muni}:**")
        zoning_lines.append(f"- {row[1]}: {row[2]} ({row[3]})")

    return {
        "counties_section": "\n".join(counties_lines),
        "layers_section": "\n".join(layers_lines),
        "zoning_section": "\n".join(zoning_lines),
    }
