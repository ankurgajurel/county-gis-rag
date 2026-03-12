"""Seed zoning districts for demonstration. In production, these come from Municode/eCode360 API access."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.db.engine import async_session
from src.db.models import Municipality, ZoningDistrict

logger = logging.getLogger(__name__)

SEED_DATA = {
    "Naperville": [
        {"code": "R1", "name": "Single-Family Residence District", "category": "residential",
         "regulations": {"min_lot_size_sqft": 10000, "max_height_ft": 30, "front_setback_ft": 30, "side_setback_ft": 10, "rear_setback_ft": 30}},
        {"code": "R2", "name": "Single-Family Residence District", "category": "residential",
         "regulations": {"min_lot_size_sqft": 7500, "max_height_ft": 30, "front_setback_ft": 25, "side_setback_ft": 7, "rear_setback_ft": 25}},
        {"code": "R3", "name": "Two-Family Residence District", "category": "residential",
         "regulations": {"min_lot_size_sqft": 6000, "max_height_ft": 35, "front_setback_ft": 25, "side_setback_ft": 7, "rear_setback_ft": 25}},
        {"code": "R4", "name": "Multiple-Family Residence District", "category": "residential",
         "regulations": {"min_lot_size_sqft": 4000, "max_height_ft": 45, "front_setback_ft": 25, "side_setback_ft": 10, "rear_setback_ft": 25}},
        {"code": "B1", "name": "Neighborhood Business District", "category": "commercial",
         "regulations": {"max_height_ft": 35, "front_setback_ft": 0, "floor_area_ratio": 1.0}},
        {"code": "B2", "name": "Community Shopping Center District", "category": "commercial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 25, "floor_area_ratio": 1.5}},
        {"code": "B3", "name": "General Commercial District", "category": "commercial",
         "regulations": {"max_height_ft": 60, "front_setback_ft": 0, "floor_area_ratio": 2.0}},
        {"code": "OCI", "name": "Office-Commercial-Industrial District", "category": "commercial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 30, "floor_area_ratio": 1.0}},
        {"code": "I", "name": "Industrial District", "category": "industrial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 40, "side_setback_ft": 20}},
    ],
    "Wheaton": [
        {"code": "R-1", "name": "Single-Family Detached Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 15000, "max_height_ft": 35, "front_setback_ft": 35}},
        {"code": "R-2", "name": "Single-Family Detached Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 10000, "max_height_ft": 35, "front_setback_ft": 30}},
        {"code": "R-3", "name": "Single and Two-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 7500, "max_height_ft": 35, "front_setback_ft": 25}},
        {"code": "R-4", "name": "Multi-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 5000, "max_height_ft": 45, "front_setback_ft": 25}},
        {"code": "C-1", "name": "Neighborhood Commercial", "category": "commercial",
         "regulations": {"max_height_ft": 35, "front_setback_ft": 10}},
        {"code": "C-2", "name": "General Commercial", "category": "commercial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 0}},
        {"code": "C-3", "name": "Central Business District", "category": "commercial",
         "regulations": {"max_height_ft": 65, "front_setback_ft": 0, "floor_area_ratio": 3.0}},
        {"code": "M-1", "name": "Limited Manufacturing", "category": "industrial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 30}},
    ],
    "Downers Grove": [
        {"code": "R-1", "name": "Single-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 12000, "max_height_ft": 35, "front_setback_ft": 30, "side_setback_ft": 10}},
        {"code": "R-2", "name": "Single-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 8400, "max_height_ft": 35, "front_setback_ft": 25, "side_setback_ft": 7}},
        {"code": "R-3", "name": "Single-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 6000, "max_height_ft": 35, "front_setback_ft": 25}},
        {"code": "R-4", "name": "Two-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 5000, "max_height_ft": 35, "front_setback_ft": 25}},
        {"code": "R-5", "name": "Multi-Family Residential", "category": "residential",
         "regulations": {"min_lot_size_sqft": 3500, "max_height_ft": 45, "front_setback_ft": 25}},
        {"code": "B-1", "name": "Limited Retail Business", "category": "commercial",
         "regulations": {"max_height_ft": 40, "front_setback_ft": 0}},
        {"code": "B-2", "name": "General Retail Business", "category": "commercial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 0, "floor_area_ratio": 2.0}},
        {"code": "B-3", "name": "General Services and Highway Business", "category": "commercial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 25}},
        {"code": "DB", "name": "Downtown Business", "category": "commercial",
         "regulations": {"max_height_ft": 65, "front_setback_ft": 0, "floor_area_ratio": 3.5}},
        {"code": "M", "name": "Manufacturing", "category": "industrial",
         "regulations": {"max_height_ft": 45, "front_setback_ft": 40, "side_setback_ft": 20}},
    ],
}


async def seed_zoning_districts():
    async with async_session() as db:
        result = await db.execute(select(Municipality))
        municipalities = {m.name: m.id for m in result.scalars().all()}

    seeded = 0
    for muni_name, districts in SEED_DATA.items():
        muni_id = municipalities.get(muni_name)
        if not muni_id:
            logger.warning("Municipality %s not found, skipping", muni_name)
            continue

        async with async_session() as db:
            for d in districts:
                stmt = insert(ZoningDistrict).values(
                    municipality_id=muni_id,
                    code=d["code"],
                    name=d["name"],
                    category=d["category"],
                    regulations=d["regulations"],
                    source_url=f"https://library.municode.com/il",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["municipality_id", "code"],
                    set_={
                        "name": stmt.excluded.name,
                        "category": stmt.excluded.category,
                        "regulations": stmt.excluded.regulations,
                    },
                )
                await db.execute(stmt)
                seeded += 1

            await db.commit()

        logger.info("Seeded %d zoning districts for %s", len(districts), muni_name)

    logger.info("Total seeded: %d zoning districts", seeded)
