"""Ingestion orchestrator: discover → fetch → normalize → store."""

import logging
from datetime import datetime, timezone

import aiohttp
from geoalchemy2 import WKTElement
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from src.db.engine import async_session
from src.db.models import (
    County,
    DataSource,
    DiscoveredLayer,
    GISFeature,
    IngestionRun,
    Parcel,
)
from src.discovery.crawler import ArcGISCrawler, save_discovered_layers
from src.ingestion.fetcher import FeatureFetcher
from src.ingestion.normalizer import normalize_gis_features, normalize_parcels
from src.providers.base import BaseProvider
from src.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


async def run_pipeline(provider: BaseProvider, full: bool = True):
    cfg = provider.config()
    logger.info("Starting pipeline for %s (full=%s)", cfg.name, full)

    rate_limiter = RateLimiter(rate=cfg.rate_limit, burst=int(cfg.rate_limit * 2))

    async with aiohttp.ClientSession() as session:
        county_id, data_source_id = await _ensure_county_and_source(cfg)

        crawler = ArcGISCrawler(session, rate_limiter)
        layers = await crawler.discover_all(cfg.arcgis_base_url)

        async with async_session() as db:
            saved = await save_discovered_layers(db, data_source_id, layers)
            logger.info("Saved %d discovered layers", saved)

        if cfg.parcel_service:
            await _ingest_parcels(
                session, rate_limiter, provider, county_id, data_source_id
            )

        logger.info("Pipeline complete for %s", cfg.name)


async def _ensure_county_and_source(cfg) -> tuple[int, int]:
    async with async_session() as db:
        result = await db.execute(
            select(County).where(County.fips_code == cfg.fips_code)
        )
        county = result.scalar_one_or_none()

        if not county:
            county = County(
                fips_code=cfg.fips_code,
                state_fips=cfg.state_fips,
                name=cfg.name,
                state=cfg.state,
                arcgis_base_url=cfg.arcgis_base_url,
                hub_url=cfg.hub_url,
            )
            db.add(county)
            await db.flush()

        result = await db.execute(
            select(DataSource).where(
                DataSource.county_id == county.id,
                DataSource.base_url == cfg.arcgis_base_url,
            )
        )
        source = result.scalar_one_or_none()

        if not source:
            source = DataSource(
                county_id=county.id,
                source_type="arcgis",
                base_url=cfg.arcgis_base_url,
                name=f"{cfg.name} ArcGIS",
                is_active=True,
            )
            db.add(source)
            await db.flush()

        await db.commit()
        return county.id, source.id


async def _ingest_parcels(
    session: aiohttp.ClientSession,
    rate_limiter: RateLimiter,
    provider: BaseProvider,
    county_id: int,
    data_source_id: int,
):
    cfg = provider.config()
    parts = cfg.parcel_service.split("/")
    if len(parts) >= 2:
        service_name = "/".join(parts[:-1]) if "/" in cfg.parcel_service else parts[0]
        service_type = cfg.parcel_service_type
    else:
        service_name = parts[0]
        service_type = cfg.parcel_service_type

    async with async_session() as db:
        result = await db.execute(
            select(DiscoveredLayer).where(
                DiscoveredLayer.data_source_id == data_source_id,
                DiscoveredLayer.service_name == service_name,
                DiscoveredLayer.service_type == service_type,
                DiscoveredLayer.layer_id == 0,
            )
        )
        layer = result.scalar_one_or_none()
        if not layer:
            logger.error("Parcel layer not found in discovered layers for %s", cfg.name)
            return

        run = IngestionRun(
            county_id=county_id,
            layer_id=layer.id,
            run_type="full",
            status="running",
        )
        db.add(run)
        await db.commit()
        run_id = run.id
        source_layer_id = layer.id
        max_record_count = layer.max_record_count or 1000

    try:
        fetcher = FeatureFetcher(session, rate_limiter)
        features = await fetcher.fetch_all(
            cfg.arcgis_base_url,
            service_name,
            service_type,
            layer_id=0,
            max_record_count=max_record_count,
        )

        logger.info("Fetched %d parcel features for %s", len(features), cfg.name)

        rows = normalize_parcels(
            provider, features, county_id, source_layer_id, run_id
        )

        stored, failed = await _store_parcels(rows)

        async with async_session() as db:
            await db.execute(
                update(IngestionRun)
                .where(IngestionRun.id == run_id)
                .values(
                    status="completed",
                    features_fetched=len(features),
                    features_stored=stored,
                    features_failed=failed,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(
                update(DiscoveredLayer)
                .where(DiscoveredLayer.id == source_layer_id)
                .values(last_ingested_at=datetime.now(timezone.utc))
            )
            await db.commit()

        logger.info(
            "Parcel ingestion done: fetched=%d stored=%d failed=%d",
            len(features), stored, failed,
        )

    except Exception as e:
        logger.error("Parcel ingestion failed for %s: %s", cfg.name, e)
        async with async_session() as db:
            await db.execute(
                update(IngestionRun)
                .where(IngestionRun.id == run_id)
                .values(
                    status="failed",
                    error_log={"error": str(e)},
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        raise


async def _store_parcels(rows: list[dict]) -> tuple[int, int]:
    stored = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]

        async with async_session() as db:
            try:
                for row in batch:
                    wkt = row.pop("geom", None)
                    geom_elem = WKTElement(wkt, srid=4326) if wkt else None

                    stmt = insert(Parcel).values(**row, geom=geom_elem)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["county_id", "pin"],
                        set_={
                            "prop_address": stmt.excluded.prop_address,
                            "prop_city": stmt.excluded.prop_city,
                            "prop_state": stmt.excluded.prop_state,
                            "prop_zip": stmt.excluded.prop_zip,
                            "owner_name": stmt.excluded.owner_name,
                            "property_class": stmt.excluded.property_class,
                            "class_description": stmt.excluded.class_description,
                            "assessed_value_land": stmt.excluded.assessed_value_land,
                            "assessed_value_bldg": stmt.excluded.assessed_value_bldg,
                            "assessed_value_total": stmt.excluded.assessed_value_total,
                            "tax_code": stmt.excluded.tax_code,
                            "tax_rate": stmt.excluded.tax_rate,
                            "tax_amount": stmt.excluded.tax_amount,
                            "acreage": stmt.excluded.acreage,
                            "land_sqft": stmt.excluded.land_sqft,
                            "bldg_sqft": stmt.excluded.bldg_sqft,
                            "bldg_age": stmt.excluded.bldg_age,
                            "lot_dimensions": stmt.excluded.lot_dimensions,
                            "municipality": stmt.excluded.municipality,
                            "township": stmt.excluded.township,
                            "legal_description": stmt.excluded.legal_description,
                            "geom": stmt.excluded.geom,
                            "raw_attributes": stmt.excluded.raw_attributes,
                            "source_layer_id": stmt.excluded.source_layer_id,
                            "ingestion_run_id": stmt.excluded.ingestion_run_id,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                    await db.execute(stmt)

                await db.commit()
                stored += len(batch)
                logger.info("Stored batch %d-%d", i, i + len(batch))

            except Exception as e:
                logger.error("Batch %d-%d failed: %s", i, i + len(batch), e)
                await db.rollback()
                failed += len(batch)

    return stored, failed
