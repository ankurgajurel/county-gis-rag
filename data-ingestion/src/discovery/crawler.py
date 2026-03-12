"""
Recursive ArcGIS REST catalog crawler.
Walks: root → folders → services → layers
"""

import logging
from dataclasses import dataclass, field

import aiohttp

from src.utils.rate_limiter import RateLimiter
from src.utils.retry import retry

logger = logging.getLogger(__name__)

QUERYABLE_TYPES = {"MapServer", "FeatureServer"}


@dataclass
class LayerInfo:
    service_name: str
    service_type: str
    layer_id: int
    layer_name: str
    geometry_type: str | None = None
    fields: list[dict] = field(default_factory=list)
    max_record_count: int = 1000
    feature_count: int | None = None
    spatial_reference: dict | None = None


class ArcGISCrawler:
    def __init__(self, session: aiohttp.ClientSession, rate_limiter: RateLimiter):
        self.session = session
        self.rate_limiter = rate_limiter

    @retry(max_attempts=3, backoff_base=2.0)
    async def _fetch_json(self, url: str, params: dict | None = None) -> dict:
        request_params = {"f": "json"}
        if params:
            request_params.update(params)

        async with self.rate_limiter:
            async with self.session.get(
                url,
                params=request_params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 429:
                    raise aiohttp.ClientError(f"Rate limited (429) on {url}")
                if resp.status >= 500:
                    raise aiohttp.ClientError(f"Server error ({resp.status}) on {url}")
                resp.raise_for_status()

                data = await resp.json(content_type=None)
                if "error" in data:
                    raise aiohttp.ClientError(f"ArcGIS error: {data['error']}")
                return data

    async def discover_all(self, base_url: str) -> list[LayerInfo]:
        logger.info("Starting discovery on %s", base_url)

        catalog = await self._fetch_json(base_url)
        folders = catalog.get("folders", [])
        root_services = catalog.get("services", [])

        logger.info("Root: %d folders, %d services", len(folders), len(root_services))

        all_layers: list[LayerInfo] = []

        for svc in root_services:
            layers = await self._discover_service(base_url, svc["name"], svc["type"])
            all_layers.extend(layers)

        for folder in folders:
            try:
                folder_catalog = await self._fetch_json(f"{base_url}/{folder}")
                folder_services = folder_catalog.get("services", [])
                logger.info("Folder '%s': %d services", folder, len(folder_services))

                for svc in folder_services:
                    layers = await self._discover_service(base_url, svc["name"], svc["type"])
                    all_layers.extend(layers)
            except Exception as e:
                logger.error("Failed folder '%s': %s", folder, e)

        logger.info("Discovery complete: %d layers found", len(all_layers))
        return all_layers

    async def _discover_service(
        self, base_url: str, name: str, svc_type: str
    ) -> list[LayerInfo]:
        if svc_type not in QUERYABLE_TYPES:
            return []

        try:
            url = f"{base_url}/{name}/{svc_type}"
            metadata = await self._fetch_json(url)
            raw_layers = metadata.get("layers", [])
            if not raw_layers:
                return []

            layers: list[LayerInfo] = []
            for layer_ref in raw_layers:
                if layer_ref.get("subLayerIds"):
                    continue

                layer = await self._discover_layer(
                    base_url, name, svc_type, layer_ref["id"], layer_ref["name"]
                )
                if layer:
                    layers.append(layer)

            logger.info("%s/%s: %d layers", name, svc_type, len(layers))
            return layers

        except Exception as e:
            logger.error("Failed service %s/%s: %s", name, svc_type, e)
            return []

    async def _discover_layer(
        self,
        base_url: str,
        service_name: str,
        service_type: str,
        layer_id: int,
        layer_name: str,
    ) -> LayerInfo | None:
        try:
            url = f"{base_url}/{service_name}/{service_type}/{layer_id}"
            detail = await self._fetch_json(url)

            geometry_type = detail.get("geometryType")
            fields = detail.get("fields", [])
            if not fields:
                return None

            feature_count = None
            try:
                count_data = await self._fetch_json(
                    f"{url}/query",
                    params={"where": "1=1", "returnCountOnly": "true"},
                )
                feature_count = count_data.get("count")
            except Exception:
                pass

            spatial_ref = detail.get("sourceSpatialReference") or detail.get(
                "spatialReference"
            )

            return LayerInfo(
                service_name=service_name,
                service_type=service_type,
                layer_id=layer_id,
                layer_name=layer_name,
                geometry_type=geometry_type,
                fields=fields,
                max_record_count=detail.get("maxRecordCount", 1000),
                feature_count=feature_count,
                spatial_reference=spatial_ref,
            )

        except Exception as e:
            logger.error("Failed layer %s/%s/%d: %s", service_name, service_type, layer_id, e)
            return None


async def save_discovered_layers(session, data_source_id: int, layers: list[LayerInfo]) -> int:
    """Upsert discovered layers to DB. Re-running updates metadata instead of duplicating."""
    from sqlalchemy.dialects.postgresql import insert
    from src.db.models import DiscoveredLayer

    saved = 0
    for layer in layers:
        stmt = insert(DiscoveredLayer).values(
            data_source_id=data_source_id,
            service_name=layer.service_name,
            service_type=layer.service_type,
            layer_id=layer.layer_id,
            layer_name=layer.layer_name,
            geometry_type=layer.geometry_type,
            field_schema=layer.fields,
            max_record_count=layer.max_record_count,
            feature_count=layer.feature_count,
            spatial_reference=layer.spatial_reference,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["data_source_id", "service_name", "service_type", "layer_id"],
            set_={
                "layer_name": stmt.excluded.layer_name,
                "geometry_type": stmt.excluded.geometry_type,
                "field_schema": stmt.excluded.field_schema,
                "max_record_count": stmt.excluded.max_record_count,
                "feature_count": stmt.excluded.feature_count,
                "spatial_reference": stmt.excluded.spatial_reference,
            },
        )
        await session.execute(stmt)
        saved += 1

    await session.commit()
    logger.info("Saved %d layers to database", saved)
    return saved
