"""Abstract base for county providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ZoningLayerConfig:
    service_name: str
    service_type: str = "MapServer"
    layer_id: int = 0
    zone_code_field: str = "ZONING"
    zone_name_field: str | None = None


@dataclass
class CountyConfig:
    fips_code: str
    name: str
    state: str
    state_fips: str
    arcgis_base_url: str
    hub_url: str | None = None
    rate_limit: float = 5.0
    parcel_service: str | None = None  # e.g. "parcel_current_beta/FeatureServer/0"
    parcel_service_type: str = "FeatureServer"
    zoning_layers: list[ZoningLayerConfig] | None = None


class BaseProvider(ABC):
    @abstractmethod
    def config(self) -> CountyConfig:
        ...

    @abstractmethod
    def normalize_parcel(self, raw: dict) -> dict:
        """Map raw ArcGIS attributes to normalized parcel columns."""
        ...

    def _join(self, *parts: str | None, sep: str = " ") -> str | None:
        """Join non-empty strings. Used for building addresses from components."""
        filtered = [p.strip() for p in parts if p and p.strip()]
        return sep.join(filtered) if filtered else None

    def _concat_legal(self, raw: dict, prefix: str, count: int) -> str | None:
        """Concatenate numbered fields like LEGALDES1..LEGALDES9."""
        parts = []
        for i in range(1, count + 1):
            val = raw.get(f"{prefix}{i}")
            if val and str(val).strip():
                parts.append(str(val).strip())
        return " ".join(parts) if parts else None
