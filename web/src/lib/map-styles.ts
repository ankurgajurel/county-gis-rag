import type { LayerSpecification } from "maplibre-gl";

export const BASEMAP_STYLE =
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

export const DEFAULT_CENTER: [number, number] = [-88.07, 41.85]; // DuPage County, IL
export const DEFAULT_ZOOM = 11;

const PARCEL_COLOR = "#3b82f6";
const ZONING_COLOR = "#f59e0b";
const OTHER_COLOR = "#6b7280";

export const SOURCE_ID = "geojson-data";

export const FILL_LAYER: LayerSpecification = {
  id: "geojson-fill",
  type: "fill",
  source: SOURCE_ID,
  filter: ["any", ["==", "$type", "Polygon"], ["==", "$type", "MultiPolygon"]],
  paint: {
    "fill-color": [
      "case",
      ["==", ["get", "source"], "parcel"],
      PARCEL_COLOR,
      [
        "any",
        ["==", ["get", "source"], "zoning"],
        [
          "in",
          "zoning",
          ["downcase", ["coalesce", ["get", "layer_name"], ""]],
        ],
      ],
      ZONING_COLOR,
      OTHER_COLOR,
    ],
    "fill-opacity": [
      "case",
      ["==", ["get", "source"], "parcel"],
      0.2,
      [
        "any",
        ["==", ["get", "source"], "zoning"],
        [
          "in",
          "zoning",
          ["downcase", ["coalesce", ["get", "layer_name"], ""]],
        ],
      ],
      0.15,
      0.1,
    ],
  },
};

export const LINE_LAYER: LayerSpecification = {
  id: "geojson-line",
  type: "line",
  source: SOURCE_ID,
  filter: [
    "any",
    ["==", "$type", "Polygon"],
    ["==", "$type", "MultiPolygon"],
    ["==", "$type", "LineString"],
    ["==", "$type", "MultiLineString"],
  ],
  paint: {
    "line-color": [
      "case",
      ["==", ["get", "source"], "parcel"],
      PARCEL_COLOR,
      [
        "any",
        ["==", ["get", "source"], "zoning"],
        [
          "in",
          "zoning",
          ["downcase", ["coalesce", ["get", "layer_name"], ""]],
        ],
      ],
      ZONING_COLOR,
      OTHER_COLOR,
    ],
    "line-width": 2,
  },
};

export const CIRCLE_LAYER: LayerSpecification = {
  id: "geojson-circle",
  type: "circle",
  source: SOURCE_ID,
  filter: ["==", "$type", "Point"],
  paint: {
    "circle-radius": 6,
    "circle-color": [
      "case",
      ["==", ["get", "source"], "parcel"],
      PARCEL_COLOR,
      OTHER_COLOR,
    ],
    "circle-stroke-width": 1.5,
    "circle-stroke-color": "#ffffff",
  },
};
