"""PostGIS schema models."""

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
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class County(Base):
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

    data_sources: Mapped[list["DataSource"]] = relationship(back_populates="county")
    parcels: Mapped[list["Parcel"]] = relationship(back_populates="county")
    gis_features: Mapped[list["GISFeature"]] = relationship(back_populates="county")
    municipalities: Mapped[list["Municipality"]] = relationship(back_populates="county")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="data_sources")
    discovered_layers: Mapped[list["DiscoveredLayer"]] = relationship(back_populates="data_source")


class DiscoveredLayer(Base):
    __tablename__ = "discovered_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_type: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry_type: Mapped[str | None] = mapped_column(String(50))
    field_schema: Mapped[dict | None] = mapped_column(JSONB)
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
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    layer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_layers.id"))
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    features_fetched: Mapped[int] = mapped_column(Integer, default=0)
    features_stored: Mapped[int] = mapped_column(Integer, default=0)
    features_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)


class Parcel(Base):
    __tablename__ = "parcels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_layer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_layers.id"))
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))

    pin: Mapped[str] = mapped_column(String(50), nullable=False)
    prop_address: Mapped[str | None] = mapped_column(String(512))
    prop_city: Mapped[str | None] = mapped_column(String(100))
    prop_state: Mapped[str | None] = mapped_column(String(2))
    prop_zip: Mapped[str | None] = mapped_column(String(10))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    property_class: Mapped[str | None] = mapped_column(String(50))
    class_description: Mapped[str | None] = mapped_column(String(255))
    assessed_value_land: Mapped[int | None] = mapped_column(BigInteger)
    assessed_value_bldg: Mapped[int | None] = mapped_column(BigInteger)
    assessed_value_total: Mapped[int | None] = mapped_column(BigInteger)
    tax_code: Mapped[str | None] = mapped_column(String(50))
    tax_rate: Mapped[float | None] = mapped_column(Double)
    tax_amount: Mapped[float | None] = mapped_column(Double)
    acreage: Mapped[float | None] = mapped_column(Double)
    land_sqft: Mapped[float | None] = mapped_column(Double)
    bldg_sqft: Mapped[int | None] = mapped_column(Integer)
    bldg_age: Mapped[int | None] = mapped_column(Integer)
    lot_dimensions: Mapped[str | None] = mapped_column(String(255))
    municipality: Mapped[str | None] = mapped_column(String(255))
    township: Mapped[str | None] = mapped_column(String(255))
    legal_description: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    raw_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="parcels")

    __table_args__ = (
        Index("idx_parcels_county_pin", "county_id", "pin", unique=True),
        Index("idx_parcels_municipality", "municipality"),
        Index("idx_parcels_raw", "raw_attributes", postgresql_using="gin"),
    )


class GISFeature(Base):
    __tablename__ = "gis_features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    source_layer_id: Mapped[int] = mapped_column(ForeignKey("discovered_layers.id"), nullable=False)
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    layer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String(100))
    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="gis_features")

    __table_args__ = (
        Index("idx_gis_features_layer", "county_id", "source_layer_id"),
        Index("idx_gis_features_attrs", "attributes", postgresql_using="gin"),
    )


class Municipality(Base):
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fips_place_code: Mapped[str | None] = mapped_column(String(10))
    zoning_source: Mapped[str | None] = mapped_column(String(50))
    zoning_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    county: Mapped["County"] = relationship(back_populates="municipalities")
    zoning_districts: Mapped[list["ZoningDistrict"]] = relationship(back_populates="municipality")

    __table_args__ = (
        Index("uq_municipality", "county_id", "name", unique=True),
    )


class ZoningDistrict(Base):
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


EMBEDDING_DIM = 1536


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_document_chunks_source", "source_type", "source_id"),
    )
