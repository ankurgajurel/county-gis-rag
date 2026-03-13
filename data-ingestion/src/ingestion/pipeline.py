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
    ZoningGeometry,
)
from src.discovery.crawler import ArcGISCrawler, save_discovered_layers
from src.ingestion.fetcher import FeatureFetcher
from src.ingestion.normalizer import normalize_gis_features, normalize_parcels, _rings_to_wkt
from src.providers.base import BaseProvider
from src.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


async def run_pipeline(provider: BaseProvider, full: bool = True):
    cfg = provider.config()
    mode = "full" if full else "incremental"
    logger.info("Starting pipeline for %s (mode=%s)", cfg.name, mode)

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
                session, rate_limiter, provider, county_id, data_source_id,
                full=full,
            )

        await _ingest_all_layers(
            session, rate_limiter, county_id, data_source_id, cfg,
            full=full,
        )

        if cfg.zoning_layers:
            await _ingest_zoning_geometries(
                session, rate_limiter, county_id, cfg
            )

        from src.ingestion.zoning import ingest_municode_zoning
        await ingest_municode_zoning(session, cfg.fips_code, county_id)

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
    full: bool = True,
):
    cfg = provider.config()
    service_name = cfg.parcel_service
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

        last_max_oid = layer.last_max_oid
        run_type = "full" if full or not last_max_oid else "incremental"

        run = IngestionRun(
            county_id=county_id,
            layer_id=layer.id,
            run_type=run_type,
            status="running",
        )
        db.add(run)
        await db.commit()
        run_id = run.id
        source_layer_id = layer.id
        max_record_count = layer.max_record_count or 1000

    try:
        fetcher = FeatureFetcher(session, rate_limiter)

        if run_type == "incremental":
            logger.info(
                "Incremental parcel ingestion for %s (OID > %d)",
                cfg.name, last_max_oid,
            )
            features = await fetcher.fetch_incremental(
                cfg.arcgis_base_url,
                service_name,
                service_type,
                layer_id=0,
                last_oid=last_max_oid,
                max_record_count=max_record_count,
            )
        else:
            features = await fetcher.fetch_all(
                cfg.arcgis_base_url,
                service_name,
                service_type,
                layer_id=0,
                max_record_count=max_record_count,
            )

        logger.info(
            "Fetched %d parcel features for %s (%s)",
            len(features), cfg.name, run_type,
        )

        rows = normalize_parcels(
            provider, features, county_id, source_layer_id, run_id
        )

        stored, failed = await _store_parcels(rows)

        # Track the max OBJECTID we've seen
        new_max_oid = _extract_max_oid(features, last_max_oid)

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
            update_vals = {"last_ingested_at": datetime.now(timezone.utc)}
            if new_max_oid is not None:
                update_vals["last_max_oid"] = new_max_oid
            await db.execute(
                update(DiscoveredLayer)
                .where(DiscoveredLayer.id == source_layer_id)
                .values(**update_vals)
            )
            await db.commit()

        logger.info(
            "Parcel ingestion done (%s): fetched=%d stored=%d failed=%d max_oid=%s",
            run_type, len(features), stored, failed, new_max_oid,
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


MAX_FEATURES_PER_LAYER = 500_000


async def _ingest_all_layers(
    session: aiohttp.ClientSession,
    rate_limiter: RateLimiter,
    county_id: int,
    data_source_id: int,
    cfg,
    full: bool = True,
):
    async with async_session() as db:
        result = await db.execute(
            select(DiscoveredLayer).where(
                DiscoveredLayer.data_source_id == data_source_id,
            )
        )
        all_layers = result.scalars().all()

    parcel_svc = cfg.parcel_service or ""
    fetcher = FeatureFetcher(session, rate_limiter)

    ingested = 0
    skipped = 0

    for layer in all_layers:
        if layer.service_name == parcel_svc and layer.layer_id == 0:
            continue

        if layer.service_type != "FeatureServer":
            continue

        if layer.feature_count and layer.feature_count > MAX_FEATURES_PER_LAYER:
            logger.info(
                "Skipping %s/%d (%d features, exceeds %d limit)",
                layer.service_name, layer.layer_id,
                layer.feature_count, MAX_FEATURES_PER_LAYER,
            )
            skipped += 1
            continue

        if not layer.geometry_type:
            continue

        use_incremental = not full and layer.last_max_oid is not None
        run_type = "incremental" if use_incremental else "full"

        try:
            run = await _create_run(county_id, layer.id, run_type)

            if use_incremental:
                logger.info(
                    "Incremental fetch for %s/%d (OID > %d)",
                    layer.service_name, layer.layer_id, layer.last_max_oid,
                )
                features = await fetcher.fetch_incremental(
                    cfg.arcgis_base_url,
                    layer.service_name,
                    layer.service_type,
                    layer.layer_id,
                    last_oid=layer.last_max_oid,
                    max_record_count=layer.max_record_count or 1000,
                )
            else:
                features = await fetcher.fetch_all(
                    cfg.arcgis_base_url,
                    layer.service_name,
                    layer.service_type,
                    layer.layer_id,
                    max_record_count=layer.max_record_count or 1000,
                )

            if not features:
                await _finish_run(run, 0, 0, 0)
                continue

            rows = normalize_gis_features(
                features, county_id, layer.id, layer.layer_name, run,
            )

            stored, failed = await _store_gis_features(rows)
            await _finish_run(run, len(features), stored, failed)

            # Update the OID watermark
            new_max_oid = _extract_max_oid(features, layer.last_max_oid)
            async with async_session() as db:
                update_vals = {"last_ingested_at": datetime.now(timezone.utc)}
                if new_max_oid is not None:
                    update_vals["last_max_oid"] = new_max_oid
                await db.execute(
                    update(DiscoveredLayer)
                    .where(DiscoveredLayer.id == layer.id)
                    .values(**update_vals)
                )
                await db.commit()

            logger.info(
                "Ingested %s/%s/%d (%s): %d features stored",
                layer.service_name, layer.service_type, layer.layer_id,
                run_type, stored,
            )
            ingested += 1

        except Exception as e:
            logger.error(
                "Failed layer %s/%d: %s", layer.service_name, layer.layer_id, e,
            )

    logger.info(
        "All-layer ingestion: %d layers ingested, %d skipped (too large)",
        ingested, skipped,
    )


async def _create_run(county_id: int, layer_id: int, run_type: str) -> int:
    async with async_session() as db:
        run = IngestionRun(
            county_id=county_id, layer_id=layer_id,
            run_type=run_type, status="running",
        )
        db.add(run)
        await db.commit()
        return run.id


async def _finish_run(
    run_id: int, fetched: int, stored: int, failed: int,
):
    async with async_session() as db:
        await db.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="completed" if failed == 0 else "partial",
                features_fetched=fetched,
                features_stored=stored,
                features_failed=failed,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


def _extract_max_oid(features: list[dict], current_max: int | None = None) -> int | None:
    """Extract the highest OBJECTID from a batch of features."""
    max_oid = current_max
    for feat in features:
        attrs = feat.get("attributes", {})
        oid = attrs.get("OBJECTID") or attrs.get("objectid") or attrs.get("FID")
        if oid is not None:
            oid = int(oid)
            if max_oid is None or oid > max_oid:
                max_oid = oid
    return max_oid


async def _store_gis_features(rows: list[dict]) -> tuple[int, int]:
    stored = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]

        async with async_session() as db:
            try:
                for row in batch:
                    wkt = row.pop("geom", None)
                    geom_elem = WKTElement(wkt, srid=4326) if wkt else None
                    db.add(GISFeature(**row, geom=geom_elem))

                await db.commit()
                stored += len(batch)

            except Exception as e:
                logger.error("GIS feature batch %d-%d failed: %s", i, i + len(batch), e)
                await db.rollback()
                failed += len(batch)

    return stored, failed


async def _ingest_zoning_geometries(
    session: aiohttp.ClientSession,
    rate_limiter: RateLimiter,
    county_id: int,
    cfg,
):
    fetcher = FeatureFetcher(session, rate_limiter)

    for zl in cfg.zoning_layers:
        try:
            query_url = (
                f"{cfg.arcgis_base_url}/{zl.service_name}"
                f"/{zl.service_type}/{zl.layer_id}/query"
            )
            logger.info(
                "Fetching zoning geometries from %s/%s/%d",
                zl.service_name, zl.service_type, zl.layer_id,
            )

            all_features = []
            offset = 0
            while True:
                params = {
                    "where": "1=1",
                    "outFields": "*",
                    "outSR": 4326,
                    "f": "json",
                    "resultOffset": offset,
                    "resultRecordCount": 1000,
                }
                async with rate_limiter:
                    async with session.get(
                        query_url, params=params,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)

                features = data.get("features", [])
                if not features:
                    break

                all_features.extend(features)
                offset += len(features)
                logger.info(
                    "Fetched %d zoning features (total: %d)",
                    len(features), len(all_features),
                )

                if not data.get("exceededTransferLimit", False):
                    break

            rows = []
            for feat in all_features:
                attrs = feat.get("attributes", {})
                geom = feat.get("geometry")
                zone_code = str(attrs.get(zl.zone_code_field, "")).strip() or None

                if not zone_code:
                    continue

                rows.append({
                    "county_id": county_id,
                    "zone_code": zone_code,
                    "attributes": attrs,
                    "geom": _rings_to_wkt(geom) if geom else None,
                })

            stored, failed = await _store_zoning_geometries(rows)
            logger.info(
                "Zoning geometry ingestion: %d stored, %d failed for %s",
                stored, failed, zl.service_name,
            )

        except Exception as e:
            logger.error(
                "Failed zoning geometry ingestion for %s: %s",
                zl.service_name, e,
            )


async def _store_zoning_geometries(rows: list[dict]) -> tuple[int, int]:
    stored = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]

        async with async_session() as db:
            try:
                for row in batch:
                    wkt = row.pop("geom", None)
                    geom_elem = WKTElement(wkt, srid=4326) if wkt else None
                    db.add(ZoningGeometry(**row, geom=geom_elem))

                await db.commit()
                stored += len(batch)

            except Exception as e:
                logger.error(
                    "Zoning geometry batch %d-%d failed: %s",
                    i, i + len(batch), e,
                )
                await db.rollback()
                failed += len(batch)

    return stored, failed


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
