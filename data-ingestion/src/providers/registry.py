"""Provider registry. Lookup by county name or FIPS code."""

from src.providers.base import BaseProvider
from src.providers.cook import CookProvider
from src.providers.dupage import DuPageProvider

_PROVIDERS: dict[str, type[BaseProvider]] = {
    "cook": CookProvider,
    "dupage": DuPageProvider,
}

_FIPS_MAP: dict[str, str] = {
    "17031": "cook",
    "17043": "dupage",
}


def get_provider(name_or_fips: str) -> BaseProvider:
    key = _FIPS_MAP.get(name_or_fips, name_or_fips).lower()
    if key not in _PROVIDERS:
        raise ValueError(f"Unknown county: {name_or_fips}. Available: {list(_PROVIDERS.keys())}")
    return _PROVIDERS[key]()


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())
