"""OpenAI Responses API function tool schemas."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "lookup_parcel",
        "description": "Look up a parcel by PIN (parcel identification number) or street address. Returns parcel details including owner, assessed value, lot size, and municipality. By default includes GeoJSON geometry for map display.",
        "parameters": {
            "type": "object",
            "properties": {
                "pin": {
                    "type": "string",
                    "description": "Parcel identification number (e.g., '06-01-102-001')",
                },
                "address": {
                    "type": "string",
                    "description": "Street address or partial address to search for",
                },
                "county": {
                    "type": "string",
                    "description": "County name to filter by (e.g., 'DuPage')",
                },
                "include_geometry": {
                    "type": "boolean",
                    "description": "Include GeoJSON geometry for map display (default true)",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "filter_parcels",
        "description": "Search parcels with multiple filters. Use this to find parcels matching specific criteria like assessed value ranges, lot sizes, property classes, or municipalities.",
        "parameters": {
            "type": "object",
            "properties": {
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
                "municipality": {
                    "type": "string",
                    "description": "Municipality/city name",
                },
                "property_class": {
                    "type": "string",
                    "description": "Property class code",
                },
                "min_assessed_value": {
                    "type": "integer",
                    "description": "Minimum total assessed value in dollars",
                },
                "max_assessed_value": {
                    "type": "integer",
                    "description": "Maximum total assessed value in dollars",
                },
                "min_land_sqft": {
                    "type": "number",
                    "description": "Minimum land area in square feet",
                },
                "max_land_sqft": {
                    "type": "number",
                    "description": "Maximum land area in square feet",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20, max 50)",
                },
            },
        },

    },
    {
        "type": "function",
        "name": "spatial_query",
        "description": "Find GIS features near a geographic point. Use this to discover what's at or near a location — flood zones, school districts, TIF districts, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {
                    "type": "number",
                    "description": "Latitude (WGS84)",
                },
                "lon": {
                    "type": "number",
                    "description": "Longitude (WGS84)",
                },
                "radius_ft": {
                    "type": "number",
                    "description": "Search radius in feet (default 100)",
                },
                "layer_name": {
                    "type": "string",
                    "description": "Filter to a specific GIS layer name",
                },
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
            },
            "required": ["lat", "lon"],
        },

    },
    {
        "type": "function",
        "name": "parcel_spatial_query",
        "description": "Find all GIS features that intersect a specific parcel's geometry. Use this to find what overlays (flood zones, zoning, school districts, etc.) apply to a parcel.",
        "parameters": {
            "type": "object",
            "properties": {
                "pin": {
                    "type": "string",
                    "description": "Parcel identification number",
                },
                "layer_name": {
                    "type": "string",
                    "description": "Filter to a specific GIS layer name",
                },
            },
            "required": ["pin"],
        },

    },
    {
        "type": "function",
        "name": "get_zoning_info",
        "description": "Look up zoning district information including regulations (setbacks, height limits, lot size, FAR) and permitted/conditional/special uses. Use this to answer questions like 'what uses are allowed in R-3 zoning' or 'what are the setbacks in Naperville B2 district'.",
        "parameters": {
            "type": "object",
            "properties": {
                "municipality": {
                    "type": "string",
                    "description": "Municipality name (e.g., 'Naperville', 'Wheaton')",
                },
                "code": {
                    "type": "string",
                    "description": "Zoning district code (e.g., 'R1', 'B2', 'C-1')",
                },
                "category": {
                    "type": "string",
                    "description": "Zoning category: residential, commercial, industrial, agricultural, mixed_use, overlay, planned_development",
                },
            },
        },

    },
    {
        "type": "function",
        "name": "get_parcel_zoning",
        "description": "Find the zoning designation for a parcel by spatially intersecting it with zoning boundary geometries. Returns the zone code, regulations, and permitted/conditional/special uses. Use this to answer 'what is the zoning for [address]?' or 'what uses are allowed at [PIN]?'",
        "parameters": {
            "type": "object",
            "properties": {
                "pin": {
                    "type": "string",
                    "description": "Parcel identification number",
                },
                "address": {
                    "type": "string",
                    "description": "Street address to search for",
                },
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "list_available_layers",
        "description": "List all available GIS data layers with their names, geometry types, and feature counts. Use this to discover what data is available before querying specific layers.",
        "parameters": {
            "type": "object",
            "properties": {
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
            },
        },

    },
    {
        "type": "function",
        "name": "query_gis_layer",
        "description": "Query a specific GIS layer by name and optionally filter by attributes. Use list_available_layers first to see what layers exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "layer_name": {
                    "type": "string",
                    "description": "Name of the GIS layer to query (partial match supported)",
                },
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
                "attribute_filter": {
                    "type": "object",
                    "description": "Key-value pairs to filter features by their attributes (uses JSONB containment)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20, max 50)",
                },
            },
            "required": ["layer_name"],
        },

    },
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for information about zoning regulations, GIS layer descriptions, field meanings, and data availability. Use this when you need to understand what a zoning code allows, find the right layer for a concept (e.g., 'flood zone'), or look up what a field name means.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'flood zone layers', 'R-1 zoning regulations Naperville', 'what fields does the parcel layer have')",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)",
                },
            },
            "required": ["query"],
        },

    },
    {
        "type": "function",
        "name": "get_geometry",
        "description": "Get geometries for map visualization as a GeoJSON FeatureCollection. Call this after lookup_parcel or spatial_query when the user would benefit from seeing results on a map. Supports lookup by parcel PIN (returns parcel + intersecting features), by GIS layer name, or by lat/lon radius.",
        "parameters": {
            "type": "object",
            "properties": {
                "pin": {
                    "type": "string",
                    "description": "Parcel PIN — returns the parcel polygon plus any intersecting GIS features",
                },
                "layer_name": {
                    "type": "string",
                    "description": "GIS layer name to fetch geometries from",
                },
                "feature_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific feature IDs to fetch (use with layer_name)",
                },
                "lat": {
                    "type": "number",
                    "description": "Latitude for radius search (WGS84)",
                },
                "lon": {
                    "type": "number",
                    "description": "Longitude for radius search (WGS84)",
                },
                "radius_ft": {
                    "type": "number",
                    "description": "Search radius in feet (default 500, used with lat/lon)",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "geocode_and_query",
        "description": "Geocode a street address and find all GIS features near it. Use this when the user provides an address and wants to know what's nearby (flood zones, school districts, etc.) without needing coordinates. Prefer this over spatial_query when the user gives an address instead of coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Full street address to geocode (e.g., '425 Fawell Blvd, Naperville, IL')",
                },
                "radius_ft": {
                    "type": "number",
                    "description": "Search radius in feet (default 500)",
                },
                "layer_name": {
                    "type": "string",
                    "description": "Filter to a specific GIS layer name",
                },
                "county": {
                    "type": "string",
                    "description": "County name to filter by",
                },
            },
            "required": ["address"],
        },
    },
]
