"""CLI entry point for the ingestion pipeline."""

import argparse
import asyncio
import sys

from src.providers.registry import get_provider, list_providers
from src.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(description="County GIS Data Ingestion")
    sub = parser.add_subparsers(dest="command")

    discover_cmd = sub.add_parser("discover", help="Discover layers for a county")
    discover_cmd.add_argument("county", help="County name or FIPS code (e.g. cook, 17031)")

    ingest_cmd = sub.add_parser("ingest", help="Run full ingestion pipeline")
    ingest_cmd.add_argument("county", help="County name or FIPS code")

    sub.add_parser("list", help="List available county providers")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging()

    if args.command == "list":
        for name in list_providers():
            print(name)
        return

    try:
        provider = get_provider(args.county)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "discover":
        asyncio.run(_discover(provider))
    elif args.command == "ingest":
        asyncio.run(_ingest(provider))


async def _discover(provider):
    import aiohttp
    from src.db.engine import async_session
    from src.discovery.crawler import ArcGISCrawler, save_discovered_layers
    from src.ingestion.pipeline import _ensure_county_and_source
    from src.utils.rate_limiter import RateLimiter

    cfg = provider.config()
    rate_limiter = RateLimiter(rate=cfg.rate_limit, burst=int(cfg.rate_limit * 2))

    async with aiohttp.ClientSession() as session:
        _, data_source_id = await _ensure_county_and_source(cfg)

        crawler = ArcGISCrawler(session, rate_limiter)
        layers = await crawler.discover_all(cfg.arcgis_base_url)

        async with async_session() as db:
            saved = await save_discovered_layers(db, data_source_id, layers)

        print(f"Discovered {len(layers)} layers, saved {saved} to database")

        for layer in layers:
            count = f" ({layer.feature_count} features)" if layer.feature_count else ""
            print(f"  {layer.service_name}/{layer.service_type}/{layer.layer_id}: {layer.layer_name}{count}")


async def _ingest(provider):
    from src.ingestion.pipeline import run_pipeline
    await run_pipeline(provider)


if __name__ == "__main__":
    main()
