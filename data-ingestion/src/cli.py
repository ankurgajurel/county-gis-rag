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
    ingest_cmd.add_argument(
        "--incremental", action="store_true",
        help="Only fetch new records since last ingestion (uses OID watermark)",
    )

    zoning_cmd = sub.add_parser("zoning", help="Ingest zoning data only")
    zoning_cmd.add_argument("county", help="County name or FIPS code")

    sub.add_parser("seed-zoning", help="Seed zoning districts for municipalities")
    sub.add_parser("list", help="List available county providers")
    sub.add_parser("embed", help="Build embeddings for RAG knowledge base")
    sub.add_parser("chat", help="Start interactive chat with the data")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging()

    if args.command == "list":
        for name in list_providers():
            print(name)
        return

    if args.command == "seed-zoning":
        asyncio.run(_seed_zoning())
        return

    if args.command == "embed":
        asyncio.run(_embed())
        return

    if args.command == "chat":
        asyncio.run(_chat())
        return

    try:
        provider = get_provider(args.county)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "discover":
        asyncio.run(_discover(provider))
    elif args.command == "ingest":
        full = not getattr(args, "incremental", False)
        asyncio.run(_ingest(provider, full=full))
    elif args.command == "zoning":
        asyncio.run(_zoning(provider))


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


async def _ingest(provider, full: bool = True):
    from src.ingestion.pipeline import run_pipeline
    await run_pipeline(provider, full=full)


async def _zoning(provider):
    import aiohttp
    from src.ingestion.pipeline import _ensure_county_and_source
    from src.ingestion.zoning import ingest_municode_zoning

    cfg = provider.config()
    county_id, _ = await _ensure_county_and_source(cfg)

    async with aiohttp.ClientSession() as session:
        await ingest_municode_zoning(session, cfg.fips_code, county_id)


async def _embed():
    from src.chat.embeddings import build_and_embed
    await build_and_embed()


async def _chat():
    from src.chat.engine import ChatEngine

    engine = ChatEngine()
    await engine.initialize()

    print("County GIS Chat (type 'quit' to exit)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nyou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        print("\nassistant: ", end="", flush=True)
        async for token in engine.chat_stream(user_input):
            print(token, end="", flush=True)
        print()


async def _seed_zoning():
    from src.ingestion.seed_zoning import seed_zoning_districts
    await seed_zoning_districts()


if __name__ == "__main__":
    main()
