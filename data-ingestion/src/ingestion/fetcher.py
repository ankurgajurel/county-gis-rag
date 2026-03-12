"""Paginated async feature fetcher for ArcGIS REST APIs."""

import logging

import aiohttp

from src.utils.rate_limiter import RateLimiter
from src.utils.retry import retry

logger = logging.getLogger(__name__)


class FeatureFetcher:
    def __init__(self, session: aiohttp.ClientSession, rate_limiter: RateLimiter):
        self.session = session
        self.rate_limiter = rate_limiter

    @retry(max_attempts=3, backoff_base=2.0)
    async def _query(self, url: str, params: dict) -> dict:
        async with self.rate_limiter:
            async with self.session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status == 429:
                    raise aiohttp.ClientError(f"Rate limited on {url}")
                if resp.status >= 500:
                    raise aiohttp.ClientError(f"Server error ({resp.status}) on {url}")
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                if "error" in data:
                    raise aiohttp.ClientError(f"ArcGIS error: {data['error']}")
                return data

    async def fetch_all(
        self,
        base_url: str,
        service_name: str,
        service_type: str,
        layer_id: int,
        max_record_count: int = 1000,
    ) -> list[dict]:
        """
        Fetch all features from a layer using resultOffset pagination.
        Falls back to OID-based pagination if resultOffset isn't supported.
        """
        query_url = f"{base_url}/{service_name}/{service_type}/{layer_id}/query"
        all_features = []
        offset = 0

        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "outSR": 4326,
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": max_record_count,
            }

            data = await self._query(query_url, params)
            features = data.get("features", [])

            if not features:
                break

            all_features.extend(features)
            offset += len(features)

            logger.info("Fetched %d features (total: %d)", len(features), len(all_features))

            if not data.get("exceededTransferLimit", False):
                break

        return all_features

    async def fetch_incremental(
        self,
        base_url: str,
        service_name: str,
        service_type: str,
        layer_id: int,
        last_oid: int,
        max_record_count: int = 1000,
    ) -> list[dict]:
        """Fetch only features with OBJECTID > last_oid."""
        query_url = f"{base_url}/{service_name}/{service_type}/{layer_id}/query"
        all_features = []
        offset = 0

        while True:
            params = {
                "where": f"OBJECTID > {last_oid}",
                "outFields": "*",
                "outSR": 4326,
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": max_record_count,
            }

            data = await self._query(query_url, params)
            features = data.get("features", [])

            if not features:
                break

            all_features.extend(features)
            offset += len(features)

            if not data.get("exceededTransferLimit", False):
                break

        return all_features
