"""
PostGIS schema models.

Design principles:
- County-agnostic: adding a new county = inserting a row, not changing schema
- Dual storage: normalized columns for cross-county queries + raw JSONB for full fidelity
- Layer-aware: every feature traces back to which service/layer it came from
- Auditable: every ingestion run is tracked with counts and error logs
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# =============================================================================
# REFERENCE TABLES
# =============================================================================


class County(Base):
    """
    One row per county. This is the top-level entity.

    To add a new county, insert a row here with its FIPS code and ArcGIS base URL.
    Everything else (discovery, ingestion, parcels) hangs off this.

    FIPS codes are the standard US county identifiers:
    - Cook County, IL = 17031
    - DuPage County, IL = 17043
    """

    __tablename__ = "counties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fips_code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    arcgis_base_url: Mapped[str | None] = mapped_column(String(512))
    hub_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    data_sources: Mapped[list["DataSource"]] = relationship(back_populates="county")
    parcels: Mapped[list["Parcel"]] = relationship(back_populates="county")
    gis_features: Mapped[list["GISFeature"]] = relationship(back_populates="county")
    municipalities: Mapped[list["Municipality"]] = relationship(back_populates="county")


class DataSource(Base):
    """
    Each county can have multiple data backends.

    DuPage has one ArcGIS REST endpoint. Cook has ArcGIS + Socrata Open Data.
    A municipality might have Municode or eCode360. This table tracks them all
    so we know where each piece of data came from.
    """

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # arcgis_rest, socrata, municode, ecode360
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="data_sources")
    discovered_layers: Mapped[list["DiscoveredLayer"]] = relationship(back_populates="data_source")


# =============================================================================
# DISCOVERY & INGESTION TRACKING
# =============================================================================


class DiscoveredLayer(Base):
    """
    Every layer the crawler finds gets a row here.

    When we crawl DuPage's ArcGIS, we find ~100+ layers across 25 folders.
    Each one is recorded with its field schema, geometry type, and record count.
    This serves as our "inventory" — we know what's available before ingesting.

    Also used for incremental ingestion: check last_ingested_at to know
    if we need to re-pull a layer.
    """

    __tablename__ = "discovered_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_type: Mapped[str] = mapped_column(String(50), nullable=False)  # MapServer, FeatureServer
    layer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry_type: Mapped[str | None] = mapped_column(String(50))  # esriGeometryPolygon, etc.
    field_schema: Mapped[dict | None] = mapped_column(JSONB)  # Full field definitions from API
    max_record_count: Mapped[int] = mapped_column(Integer, default=1000)
    feature_count: Mapped[int | None] = mapped_column(Integer)
    spatial_reference: Mapped[dict | None] = mapped_column(JSONB)
    is_queryable: Mapped[bool] = mapped_column(Boolean, default=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    data_source: Mapped["DataSource"] = relationship(back_populates="discovered_layers")

    __table_args__ = (
        Index(
            "uq_discovered_layer",
            "data_source_id", "service_name", "service_type", "layer_id",
            unique=True,
        ),
    )


class IngestionRun(Base):
    """
    Audit log for every pipeline execution.

    Tracks: what county, which layer, how many features fetched/stored/failed,
    and any errors. Status can be: running, completed, failed, partial.

    'partial' means some layers succeeded but others failed — the pipeline
    didn't stop, it kept going and logged the errors.
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    layer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_layers.id"))
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)  # full, incremental, discovery
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    features_fetched: Mapped[int] = mapped_column(Integer, default=0)
    features_stored: Mapped[int] = mapped_column(Integer, default=0)
    features_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)


# =============================================================================
# PARCEL DATA
# =============================================================================


class Parcel(Base):
    """
    The core table. One row per parcel per county.

    Normalized columns cover the ~20 fields both Cook and DuPage share:
    PIN, address, valuation, property class, tax info, municipality, etc.

    raw_attributes JSONB preserves ALL original fields (83 for DuPage, 115 for Cook)
    exactly as received. Nothing is lost. This lets the RAG chat query any field
    even if we didn't normalize it.

    The UNIQUE constraint on (county_id, pin) enables idempotent upserts:
    re-running ingestion updates existing parcels instead of duplicating them.
    """

    __tablename__ = "parcels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_layer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_layers.id"))
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))

    # Parcel identifier
    pin: Mapped[str] = mapped_column(String(50), nullable=False)

    # Property address — normalized
    # DuPage: concatenated from PROPSTNUM + PROPSTDIR + PROPSTNAME
    # Cook: directly from street_address field
    prop_address: Mapped[str | None] = mapped_column(String(512))
    prop_city: Mapped[str | None] = mapped_column(String(100))
    prop_state: Mapped[str | None] = mapped_column(String(2))
    prop_zip: Mapped[str | None] = mapped_column(String(10))

    # Owner info (DuPage has BILLNAME, Cook doesn't expose on parcel layer)
    owner_name: Mapped[str | None] = mapped_column(String(255))

    # Property classification
    # DuPage: REA017_PROP_CLASS, Cook: BCLASS
    property_class: Mapped[str | None] = mapped_column(String(50))
    class_description: Mapped[str | None] = mapped_column(String(255))

    # Assessed values
    # DuPage: REA017_FCV_LAND/IMP/TOTAL, Cook: CURRENTVALUE_LAND/BLDG/TOTAL
    assessed_value_land: Mapped[int | None] = mapped_column(BigInteger)
    assessed_value_bldg: Mapped[int | None] = mapped_column(BigInteger)
    assessed_value_total: Mapped[int | None] = mapped_column(BigInteger)

    # Tax info (DuPage has rate/amount, Cook doesn't on parcel layer)
    tax_code: Mapped[str | None] = mapped_column(String(50))
    tax_rate: Mapped[float | None] = mapped_column(Double)
    tax_amount: Mapped[float | None] = mapped_column(Double)

    # Land / building measurements
    acreage: Mapped[float | None] = mapped_column(Double)
    land_sqft: Mapped[float | None] = mapped_column(Double)
    bldg_sqft: Mapped[int | None] = mapped_column(Integer)
    bldg_age: Mapped[int | None] = mapped_column(Integer)
    lot_dimensions: Mapped[str | None] = mapped_column(String(255))

    # Location
    municipality: Mapped[str | None] = mapped_column(String(255))
    township: Mapped[str | None] = mapped_column(String(255))

    # Legal description (concatenated from LEGALDES1-9 or LEGAL1-3)
    legal_description: Mapped[str | None] = mapped_column(Text)

    # Geometry — always stored as WGS84 (SRID 4326)
    # We request outSR=4326 from ArcGIS so the server reprojects for us
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    # ALL original attributes preserved exactly as received from the API
    raw_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Timestamps
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="parcels")

    __table_args__ = (
        # GeoAlchemy2 auto-creates a GIST index on geom, so we don't add one
        Index("idx_parcels_county_pin", "county_id", "pin", unique=True),
        Index("idx_parcels_municipality", "municipality"),
        Index("idx_parcels_raw", "raw_attributes", postgresql_using="gin"),
    )


# =============================================================================
# GENERIC GIS FEATURES (non-parcel layers)
# =============================================================================


class GISFeature(Base):
    """
    Catch-all for every non-parcel layer: zoning polygons, flood zones,
    school districts, TIF districts, building footprints, bus routes, etc.

    No normalized columns here — each layer has completely different attributes.
    Everything goes into the JSONB `attributes` column. The layer_name lets you
    filter by type (e.g., WHERE layer_name = 'Fire Protection District').

    Spatial index on geom enables fast spatial joins with the parcels table
    (e.g., "find all parcels within this TIF district polygon").
    """

    __tablename__ = "gis_features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_layer_id: Mapped[int] = mapped_column(ForeignKey("discovered_layers.id"), nullable=False)
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))

    layer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String(100))  # OBJECTID from source

    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="gis_features")

    __table_args__ = (
        Index("idx_gis_features_layer", "county_id", "source_layer_id"),
        Index("idx_gis_features_attrs", "attributes", postgresql_using="gin"),
    )


# =============================================================================
# MUNICIPAL ZONING
# =============================================================================


class Municipality(Base):
    """
    Municipalities within a county. Cook has 130+, DuPage has 30+.

    Zoning ordinances live at this level, not at the county level.
    Each municipality might publish their code on Municode, eCode360,
    or their own website — zoning_source tracks which.
    """

    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fips_place_code: Mapped[str | None] = mapped_column(String(10))
    zoning_source: Mapped[str | None] = mapped_column(String(50))  # municode, ecode360, county_gis
    zoning_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="municipalities")
    zoning_districts: Mapped[list["ZoningDistrict"]] = relationship(back_populates="municipality")

    __table_args__ = (
        Index("uq_municipality", "county_id", "name", unique=True),
    )


class ZoningDistrict(Base):
    """
    A zoning classification within a municipality. E.g., R-1, C-2, I-1.

    - code: the short identifier (R-1)
    - name: human-readable (Single Family Residential)
    - category: broad bucket (residential, commercial, industrial, mixed, agricultural, special)
    - regulations: JSONB with parsed rules (setbacks, FAR, height, density) — best-effort
    - raw_text: full scraped text from Municode/eCode360
    """

    __tablename__ = "zoning_districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    regulations: Mapped[dict | None] = mapped_column(JSONB)
    source_url: Mapped[str | None] = mapped_column(String(512))
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    municipality: Mapped["Municipality"] = relationship(back_populates="zoning_districts")

    __table_args__ = (
        Index("uq_zoning_district", "municipality_id", "code", unique=True),
    )


class ZoningGeometry(Base):
    """
    Spatial boundaries of zoning districts from county GIS layers.

    Links back to a zoning_district when we can match the zone_code,
    enabling spatial + text queries: "what's the zoning for this parcel?"
    (spatial join) → "what uses are permitted?" (join to zoning_districts.regulations).
    """

    __tablename__ = "zoning_geometries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zoning_district_id: Mapped[int | None] = mapped_column(ForeignKey("zoning_districts.id"))
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_layer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_layers.id"))
    zone_code: Mapped[str | None] = mapped_column(String(50))

    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__: tuple = ()
