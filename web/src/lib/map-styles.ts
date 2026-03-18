import type { StyleSpecification } from "maplibre-gl";

// ArcGIS World Imagery — satellite basemap with street labels overlay (free, no API key)
export const BASEMAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Esri, Maxar, Earthstar Geographics",
      maxzoom: 19,
    },
    labels: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "satellite",
      type: "raster",
      source: "satellite",
    },
    {
      id: "labels",
      type: "raster",
      source: "labels",
    },
  ],
};

export const DEFAULT_CENTER: [number, number] = [-88.07, 41.85]; // DuPage County, IL
export const DEFAULT_ZOOM = 11;

export const SOURCE_ID = "geojson-data";

export const FILL_LAYER_ID = "geojson-fill";
export const LINE_LAYER_ID = "geojson-line";
export const CIRCLE_LAYER_ID = "geojson-circle";

export const INTERACTIVE_LAYERS = [FILL_LAYER_ID, LINE_LAYER_ID, CIRCLE_LAYER_ID];
