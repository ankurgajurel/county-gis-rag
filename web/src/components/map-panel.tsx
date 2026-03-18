"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  BASEMAP_STYLE,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
  SOURCE_ID,
  FILL_LAYER,
  LINE_LAYER,
  CIRCLE_LAYER,
} from "@/lib/map-styles";

interface MapPanelProps {
  geojson: GeoJSON.FeatureCollection | null;
  onFeatureClick?: (properties: Record<string, unknown>) => void;
  onClose?: () => void;
}

const INTERACTIVE_LAYERS = [FILL_LAYER.id, LINE_LAYER.id, CIRCLE_LAYER.id];

export function MapPanel({ geojson, onFeatureClick, onClose }: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [isResizing, setIsResizing] = useState(false);

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

      map.addLayer(FILL_LAYER as maplibregl.LayerSpecification);
      map.addLayer(LINE_LAYER as maplibregl.LayerSpecification);
      map.addLayer(CIRCLE_LAYER as maplibregl.LayerSpecification);

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

        // Show popup
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

        onFeatureClick?.(props);
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update GeoJSON data
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const update = () => {
      const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
      if (!source) return;

      const data: GeoJSON.FeatureCollection = geojson?.features?.length
        ? geojson
        : { type: "FeatureCollection", features: [] };

      source.setData(data);

      // Fit bounds if we have features
      if (geojson?.bbox && geojson.bbox.length === 4) {
        const [minLon, minLat, maxLon, maxLat] = geojson.bbox;
        map.fitBounds(
          [
            [minLon, minLat],
            [maxLon, maxLat],
          ],
          { padding: 60, maxZoom: 17, duration: 800 }
        );
      } else if (geojson?.features?.length) {
        // Compute bounds manually
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
    };

    if (map.isStyleLoaded()) {
      update();
    } else {
      map.once("load", update);
    }
  }, [geojson]);

  // Resize map when panel resizes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const observer = new ResizeObserver(() => map.resize());
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);

      const startX = e.clientX;
      const panel = containerRef.current?.parentElement;
      if (!panel) return;
      const startWidth = panel.getBoundingClientRect().width;

      const onMouseMove = (ev: MouseEvent) => {
        const delta = startX - ev.clientX;
        const newWidth = Math.max(300, Math.min(startWidth + delta, window.innerWidth * 0.7));
        panel.style.width = `${newWidth}px`;
        panel.style.flexShrink = "0";
        mapRef.current?.resize();
      };

      const onMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    []
  );

  return (
    <div className="relative flex h-full w-full">
      {/* Resize handle */}
      <div
        onMouseDown={handleResizeStart}
        className={`absolute left-0 top-0 z-10 h-full w-1.5 cursor-col-resize transition-colors hover:bg-foreground/10 ${
          isResizing ? "bg-foreground/15" : ""
        }`}
      />

      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-md bg-background/80 text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-background hover:text-foreground"
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

      {/* Map container */}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
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
