"""Zoning ingestion: GIS geometries from ArcGIS + ordinance text from multiple sources."""

import logging
import re
from datetime import datetime, timezone

import aiohttp
from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.db.engine import async_session
from src.db.models import (
    DiscoveredLayer,
    Municipality,
    ZoningDistrict,
    ZoningGeometry,
)
from src.ingestion.normalizer import _rings_to_wkt

logger = logging.getLogger(__name__)

MUNICIPALITIES = {
    "17031": [
        {
            "name": "Evanston",
            "sources": [
                {"type": "municode", "slug": "evanston"},
                {"type": "amlegal", "slug": "evanston"},
            ],
        },
        {
            "name": "Oak Park",
            "sources": [
                {"type": "municode", "slug": "oak_park"},
            ],
        },
        {
            "name": "Schaumburg",
            "sources": [
                {"type": "municode", "slug": "schaumburg"},
            ],
        },
    ],
    "17043": [
        {
            "name": "Naperville",
            "sources": [
                {"type": "municode", "slug": "naperville"},
            ],
        },
        {
            "name": "Wheaton",
            "sources": [
                {"type": "municode", "slug": "wheaton"},
            ],
        },
        {
            "name": "Downers Grove",
            "sources": [
                {"type": "municode", "slug": "downers_grove"},
                {"type": "amlegal", "slug": "downers_grove"},
            ],
        },
    ],
}


async def ingest_municode_zoning(
    session: aiohttp.ClientSession,
    fips_code: str,
    county_id: int,
):
    munis = MUNICIPALITIES.get(fips_code, [])
    if not munis:
        logger.info("No municipalities configured for FIPS %s", fips_code)
        return

    for muni_config in munis:
        name = muni_config["name"]
        scraped = False

        for source in muni_config["sources"]:
            try:
                if source["type"] == "municode":
                    scraped = await _scrape_municode(session, county_id, name, source["slug"])
                elif source["type"] == "amlegal":
                    scraped = await _scrape_amlegal(session, county_id, name, source["slug"])

                if scraped:
                    break
            except Exception as e:
                logger.warning("Source %s failed for %s: %s", source["type"], name, e)

        if not scraped:
            logger.info("No scraping source worked for %s, creating municipality record only", name)
            await _ensure_municipality(county_id, name, "manual", None)


async def _ensure_municipality(
    county_id: int, name: str, source: str, url: str | None,
) -> int:
    async with async_session() as db:
        stmt = insert(Municipality).values(
            county_id=county_id,
            name=name,
            zoning_source=source,
            zoning_url=url,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["county_id", "name"],
            set_={"zoning_source": source, "zoning_url": url},
        )
        await db.execute(stmt)
        await db.commit()

        result = await db.execute(
            select(Municipality).where(
                Municipality.county_id == county_id,
                Municipality.name == name,
            )
        )
        return result.scalar_one().id


async def _scrape_municode(
    session: aiohttp.ClientSession,
    county_id: int,
    name: str,
    slug: str,
) -> bool:
    base_url = f"https://library.municode.com/il/{slug}"
    toc_url = f"https://library.municode.com/api/library/il/{slug}/code-of-ordinances/toc"

    try:
        async with session.get(toc_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.warning("Municode TOC not found for %s (status %d)", name, resp.status)
                return False
            toc = await resp.json()
    except (aiohttp.ClientError, OSError) as e:
        logger.warning("Municode unreachable for %s: %s", name, e)
        return False

    muni_id = await _ensure_municipality(
        county_id, name, "municode",
        f"{base_url}/codes/code_of_ordinances",
    )

    zoning_node = _find_zoning_node(toc)
    if not zoning_node:
        logger.warning("No zoning chapter found in Municode TOC for %s", name)
        return False

    logger.info("Found zoning chapter for %s: %s", name, zoning_node.get("title", ""))

    children = zoning_node.get("children", [])
    if not children:
        children = [zoning_node]

    for child in children:
        await _ingest_municode_section(session, slug, muni_id, child)

    return True


async def _ingest_municode_section(
    session: aiohttp.ClientSession,
    slug: str,
    municipality_id: int,
    node: dict,
):
    title = node.get("title", "")
    node_id = node.get("id")
    if not node_id:
        return

    code = _extract_district_code(title) or title[:50]
    category = _classify_zone(title)

    content_url = f"https://library.municode.com/api/library/il/{slug}/code-of-ordinances/node/{node_id}"
    raw_text = None

    try:
        async with session.get(content_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                raw_text = _strip_html(data.get("text") or data.get("content", ""))
    except Exception:
        pass

    await _upsert_zoning_district(municipality_id, code, title, category, content_url, raw_text)


async def _scrape_amlegal(
    session: aiohttp.ClientSession,
    county_id: int,
    name: str,
    slug: str,
) -> bool:
    base_url = f"https://codelibrary.amlegal.com/codes/{slug}il/latest/overview"

    try:
        async with session.get(base_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return False
            html = await resp.text()
    except (aiohttp.ClientError, OSError):
        return False

    muni_id = await _ensure_municipality(county_id, name, "amlegal", base_url)

    zoning_links = re.findall(
        r'href="(/codes/[^"]*?(?:zoning|zone)[^"]*)"',
        html,
        re.IGNORECASE,
    )

    if not zoning_links:
        logger.warning("No zoning links found in American Legal for %s", name)
        return False

    for link in zoning_links[:20]:
        full_url = f"https://codelibrary.amlegal.com{link}"
        try:
            async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                raw_text = _strip_html(html)

            title = re.search(r"<title>([^<]+)</title>", html)
            title_text = title.group(1) if title else link.split("/")[-1]

            code = _extract_district_code(title_text) or title_text[:50]
            category = _classify_zone(title_text)

            await _upsert_zoning_district(muni_id, code, title_text, category, full_url, raw_text)

        except Exception as e:
            logger.debug("Failed to fetch %s: %s", full_url, e)

    return True


async def _upsert_zoning_district(
    municipality_id: int,
    code: str,
    title: str,
    category: str | None,
    source_url: str,
    raw_text: str | None,
):
    regulations = _extract_regulations(raw_text) if raw_text else None

    async with async_session() as db:
        stmt = insert(ZoningDistrict).values(
            municipality_id=municipality_id,
            code=code,
            name=title,
            category=category,
            description=title,
            regulations=regulations,
            source_url=source_url,
            raw_text=raw_text[:50000] if raw_text else None,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["municipality_id", "code"],
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "regulations": stmt.excluded.regulations,
                "raw_text": stmt.excluded.raw_text,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(stmt)
        await db.commit()


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_zoning_node(toc_data) -> dict | None:
    nodes = toc_data if isinstance(toc_data, list) else toc_data.get("children", [])
    for node in nodes:
        title = (node.get("title") or "").lower()
        if "zoning" in title:
            return node
        sub = _find_zoning_node(node)
        if sub:
            return sub
    return None


def _extract_district_code(title: str) -> str | None:
    match = re.search(r'\b([A-Z]{1,3}[-\s]?\d{0,2})\b', title)
    if match:
        return match.group(1).strip()
    match = re.search(r'(?:district|zone|sec(?:tion)?\.?\s*)(\S+)', title, re.IGNORECASE)
    if match:
        return match.group(1)[:50]
    return None


def _classify_zone(title: str) -> str | None:
    t = title.lower()
    if "resident" in t:
        return "residential"
    if "commerc" in t:
        return "commercial"
    if "industr" in t or "manufactur" in t:
        return "industrial"
    if "office" in t or "business" in t:
        return "commercial"
    if "agricult" in t or "rural" in t:
        return "agricultural"
    if "mixed" in t:
        return "mixed_use"
    if "special" in t or "overlay" in t:
        return "overlay"
    if "planned" in t:
        return "planned_development"
    return None


def _extract_regulations(text: str) -> dict | None:
    if not text:
        return None

    regs = {}

    for label, key in [
        (r"front\s+(?:yard\s+)?setback", "front_setback_ft"),
        (r"rear\s+(?:yard\s+)?setback", "rear_setback_ft"),
        (r"side\s+(?:yard\s+)?setback", "side_setback_ft"),
        (r"max(?:imum)?\s+(?:building\s+)?height", "max_height_ft"),
    ]:
        match = re.search(rf"(?:{label})[:\s]+(\d+)", text, re.IGNORECASE)
        if match:
            regs[key] = int(match.group(1))

    lot = re.search(r"(?:min(?:imum)?\s+lot\s+(?:size|area))[:\s]+([\d,]+)", text, re.IGNORECASE)
    if lot:
        regs["min_lot_size_sqft"] = int(lot.group(1).replace(",", ""))

    far = re.search(r"(?:floor\s+area\s+ratio|FAR)[:\s]+([\d.]+)", text, re.IGNORECASE)
    if far:
        regs["floor_area_ratio"] = float(far.group(1))

    return regs if regs else None
