"""Converts raw ArcGIS features into database-ready rows."""

import logging
from typing import Any

from src.providers.base import BaseProvider

logger = logging.getLogger(__name__)


def normalize_parcels(
    provider: BaseProvider,
    features: list[dict],
    county_id: int,
    source_layer_id: int,
    ingestion_run_id: int,
) -> list[dict]:
    rows = []
    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry")

        normalized = provider.normalize_parcel(attrs)

        if not normalized.get("pin"):
            continue

        row = {
            "county_id": county_id,
            "source_layer_id": source_layer_id,
            "ingestion_run_id": ingestion_run_id,
            "raw_attributes": attrs,
            "geom": _rings_to_wkt(geom) if geom else None,
            **normalized,
        }
        rows.append(row)

    skipped = len(features) - len(rows)
    if skipped:
        logger.warning("Skipped %d features with no PIN", skipped)

    return rows


def normalize_gis_features(
    features: list[dict],
    county_id: int,
    source_layer_id: int,
    layer_name: str,
    ingestion_run_id: int | None = None,
) -> list[dict]:
    rows = []
    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry")

        feature_id = str(attrs.get("OBJECTID", "")) or None

        row = {
            "county_id": county_id,
            "source_layer_id": source_layer_id,
            "ingestion_run_id": ingestion_run_id,
            "layer_name": layer_name,
            "feature_id": feature_id,
            "attributes": attrs,
            "geom": _geometry_to_wkt(geom) if geom else None,
        }
        rows.append(row)

    return rows


def _rings_to_wkt(geom: dict) -> str | None:
    """Convert ArcGIS polygon geometry (rings) to MULTIPOLYGON WKT."""
    rings = geom.get("rings")
    if not rings:
        return None

    polygons = []
    for ring in rings:
        coords = ", ".join(f"{x} {y}" for x, y in ring)
        polygons.append(f"(({coords}))")

    return f"MULTIPOLYGON({', '.join(polygons)})"


def _geometry_to_wkt(geom: dict) -> str | None:
    """Convert ArcGIS geometry to WKT. Handles points, polylines, polygons."""
    if "rings" in geom:
        return _rings_to_wkt(geom)

    if "paths" in geom:
        lines = []
        for path in geom["paths"]:
            coords = ", ".join(f"{x} {y}" for x, y in path)
            lines.append(f"({coords})")
        return f"MULTILINESTRING({', '.join(lines)})"

    if "x" in geom and "y" in geom:
        return f"POINT({geom['x']} {geom['y']})"

    return None
