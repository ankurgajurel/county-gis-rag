"""DuPage County provider. FIPS 17043."""

from src.providers.base import BaseProvider, CountyConfig


class DuPageProvider(BaseProvider):
    def config(self) -> CountyConfig:
        return CountyConfig(
            fips_code="17043",
            name="DuPage County",
            state="IL",
            state_fips="17",
            arcgis_base_url="https://gis.dupageco.org/arcgis/rest/services",
            hub_url="https://gisdata-dupage.opendata.arcgis.com/",
            rate_limit=5.0,
            parcel_service="DuPage_County_IL/ParcelsWithRealEstateCC",
            parcel_service_type="FeatureServer",
        )

    def normalize_parcel(self, raw: dict) -> dict:
        return {
            "pin": raw.get("PIN"),
            "prop_address": self._join(
                raw.get("PROPSTNUM"),
                raw.get("PROPSTDIR"),
                raw.get("PROPSTNAME"),
            ),
            "prop_city": raw.get("PROPCITY"),
            "prop_state": raw.get("PROPSTATE"),
            "prop_zip": raw.get("PROPZIP"),
            "owner_name": raw.get("BILLNAME"),
            "property_class": raw.get("REA017_PROP_CLASS"),
            "class_description": None,
            "assessed_value_land": raw.get("REA017_FCV_LAND"),
            "assessed_value_bldg": raw.get("REA017_FCV_IMP"),
            "assessed_value_total": raw.get("REA017_FCV_TOTAL"),
            "tax_code": raw.get("TAXCODE"),
            "tax_rate": raw.get("TAXRATE"),
            "tax_amount": raw.get("TAXAMOUNT"),
            "acreage": raw.get("ACREAGE"),
            "land_sqft": None,
            "bldg_sqft": None,
            "bldg_age": None,
            "lot_dimensions": None,
            "municipality": raw.get("MUNICIPALITY"),
            "township": None,
            "legal_description": self._concat_legal(raw, "LEGALDES", 9),
        }
