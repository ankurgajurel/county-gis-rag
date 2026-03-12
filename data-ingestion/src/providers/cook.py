"""Cook County provider. FIPS 17031."""

from src.providers.base import BaseProvider, CountyConfig


class CookProvider(BaseProvider):
    def config(self) -> CountyConfig:
        return CountyConfig(
            fips_code="17031",
            name="Cook County",
            state="IL",
            state_fips="17",
            arcgis_base_url="https://gis12.cookcountyil.gov/arcgis/rest/services",
            hub_url="https://hub-cookcountyil.opendata.arcgis.com/",
            rate_limit=2.0,  # slower server
            parcel_service="parcel_current_beta",
            parcel_service_type="FeatureServer",
        )

    def normalize_parcel(self, raw: dict) -> dict:
        # Cook has both component fields (ADRNO, ADRDIR, ADRSTR) and
        # a pre-concatenated street_address field. Prefer the concatenated one.
        address = raw.get("street_address") or self._join(
            str(raw.get("ADRNO", "")) if raw.get("ADRNO") else None,
            raw.get("ADRDIR"),
            raw.get("ADRSTR"),
            raw.get("ADRSUF"),
        )

        return {
            "pin": raw.get("PIN14") or raw.get("PARID"),
            "prop_address": address,
            "prop_city": raw.get("CITYNAME"),
            "prop_state": raw.get("STATECODE"),
            "prop_zip": raw.get("ZIP1"),
            "owner_name": None,  # not on Cook parcel layer
            "property_class": raw.get("BCLASS"),
            "class_description": raw.get("class_description"),
            "assessed_value_land": raw.get("CURRENTVALUE_LAND"),
            "assessed_value_bldg": raw.get("CURRENTVALUE_BLDG"),
            "assessed_value_total": raw.get("CURRENTVALUE_TOTAL"),
            "tax_code": raw.get("TAXDIST"),
            "tax_rate": None,  # not on Cook parcel layer
            "tax_amount": None,
            "acreage": raw.get("ACRES"),
            "land_sqft": raw.get("LANDSF"),
            "bldg_sqft": raw.get("BLDGSQFT"),
            "bldg_age": raw.get("BLDGAGE"),
            "lot_dimensions": raw.get("LOTDIM"),
            "municipality": raw.get("CITYNAME") or raw.get("township_name"),
            "township": raw.get("township_name"),
            "legal_description": self._concat_legal(raw, "LEGAL", 3) or raw.get("LEGDESC"),
        }
