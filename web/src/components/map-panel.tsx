"use client";

import { useRef, useEffect, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  BASEMAP_STYLE,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
  SOURCE_ID,
  FILL_LAYER_ID,
  LINE_LAYER_ID,
  CIRCLE_LAYER_ID,
  INTERACTIVE_LAYERS,
} from "@/lib/map-styles";

interface MapPanelProps {
  geojson: GeoJSON.FeatureCollection | null;
  onFeatureClick?: (properties: Record<string, unknown>) => void;
  onClose?: () => void;
}

export function MapPanel({ geojson, onFeatureClick, onClose }: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const onFeatureClickRef = useRef(onFeatureClick);
  onFeatureClickRef.current = onFeatureClick;

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-left");

    map.on("load", () => {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Bright fill for polygons — stands out on satellite
      map.addLayer({
        id: FILL_LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": "#facc15",
          "fill-opacity": 0.3,
        },
      });

      // Bright outline for polygons
      map.addLayer({
        id: LINE_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": "#facc15",
          "line-width": 2.5,
        },
      });

      // Points
      map.addLayer({
        id: CIRCLE_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", "$type", "Point"],
        paint: {
          "circle-radius": 7,
          "circle-color": "#facc15",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });

      // Pointer cursor on hoverable features
      for (const layerId of INTERACTIVE_LAYERS) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
        });
      }

      // Click handler
      map.on("click", (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: INTERACTIVE_LAYERS,
        });
        if (!features.length) return;

        const props = features[0].properties || {};
        const lines: string[] = [];
        if (props.pin) lines.push(`<strong>PIN:</strong> ${props.pin}`);
        if (props.prop_address)
          lines.push(`<strong>Address:</strong> ${props.prop_address}`);
        if (props.layer_name)
          lines.push(`<strong>Layer:</strong> ${props.layer_name}`);
        if (props.municipality)
          lines.push(`<strong>Municipality:</strong> ${props.municipality}`);
        if (props.assessed_value_total)
          lines.push(
            `<strong>Assessed:</strong> $${Number(props.assessed_value_total).toLocaleString()}`
          );
        if (props.feature_id)
          lines.push(`<strong>Feature ID:</strong> ${props.feature_id}`);

        if (popupRef.current) popupRef.current.remove();
        popupRef.current = new maplibregl.Popup({ maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-size:13px;line-height:1.5">${lines.join("<br/>")}</div>`
          )
          .addTo(map);

        onFeatureClickRef.current?.(props);
      });

      // If geojson already available at mount time, set it
      if (geojson?.features?.length) {
        const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
        source?.setData(geojson);
        fitToData(map, geojson);
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update GeoJSON data when prop changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const update = () => {
      const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
      if (!source) return;

      if (geojson?.features?.length) {
        source.setData(geojson);
        fitToData(map, geojson);
      } else {
        source.setData({ type: "FeatureCollection", features: [] });
      }
    };

    if (map.isStyleLoaded()) {
      update();
    } else {
      map.once("load", update);
    }
  }, [geojson]);

  // Resize map when container resizes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const observer = new ResizeObserver(() => map.resize());
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handleRecenter = useCallback(() => {
    const map = mapRef.current;
    if (!map || !geojson?.features?.length) return;
    fitToData(map, geojson);
  }, [geojson]);

  return (
    <div className="relative h-full w-full">
      {/* Top-right controls */}
      <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5">
        {/* Recenter button */}
        <button
          onClick={handleRecenter}
          className="flex h-7 w-7 items-center justify-center rounded-md bg-background/80 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-background hover:text-foreground"
          aria-label="Recenter map"
          title="Recenter on data"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
          </svg>
        </button>

        {/* Close button */}
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md bg-background/80 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-background hover:text-foreground"
          aria-label="Close map"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {/* Map container */}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

function fitToData(
  map: maplibregl.Map,
  geojson: GeoJSON.FeatureCollection
): void {
  if (geojson.bbox && geojson.bbox.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = geojson.bbox;
    map.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 60, maxZoom: 17, duration: 800 }
    );
    return;
  }

  const bounds = new maplibregl.LngLatBounds();
  for (const f of geojson.features) {
    if (f.geometry && "coordinates" in f.geometry) {
      addCoordsToBounds(f.geometry.coordinates, bounds);
    }
  }
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 60, maxZoom: 17, duration: 800 });
  }
}

function addCoordsToBounds(
  coords: unknown,
  bounds: maplibregl.LngLatBounds
): void {
  if (!Array.isArray(coords) || coords.length === 0) return;
  if (typeof coords[0] === "number") {
    bounds.extend([coords[0] as number, coords[1] as number]);
  } else {
    for (const c of coords) {
      addCoordsToBounds(c, bounds);
    }
  }
}
