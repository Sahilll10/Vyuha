import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./CommandMap.css";

const BENGALURU_CENTER = [12.9716, 77.5946];

const SEVERITY_COLOR = { Low: "#23d18b", Medium: "#ffc24b", High: "#ff5470" };

function severityColor(severity) {
  return SEVERITY_COLOR[severity] || "#8089a0";
}

function buildIncidentIcon(severity, isSelected) {
  const color = severityColor(severity);
  const size = isSelected ? 22 : 16;
  return L.divIcon({
    className: "vy-marker-wrap",
    html: `
      <span class="vy-marker ${isSelected ? "is-selected" : ""}" style="--c:${color}; width:${size}px; height:${size}px;">
        <span class="vy-marker-ping" style="background:${color}"></span>
        <span class="vy-marker-core" style="background:${color}"></span>
      </span>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export default function CommandMap({
  events = [],
  selectedEventId = null,
  onSelectEvent = () => {},
  pickMode = false,
  onPickLocation = () => {},
  responseCard = null,
}) {
  const mapElRef = useRef(null);
  const mapRef = useRef(null);
  const markersLayerRef = useRef(null);
  const overlayLayerRef = useRef(null);

  // ── init map once ──
  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map(mapElRef.current, {
      center: BENGALURU_CENTER,
      zoom: 12,
      zoomControl: false,
      attributionControl: true,
    });
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer(
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  {
    subdomains: "abcd",
    maxZoom: 20,
    attribution:
      "&copy; OpenStreetMap contributors &copy; CARTO",
  }
).addTo(map);

    markersLayerRef.current = L.featureGroup().addTo(map);
    overlayLayerRef.current = L.featureGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ── pick-location click handler (what-if injector) ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e) => {
      if (!pickMode) return;
      onPickLocation({ lat: e.latlng.lat, lng: e.latlng.lng });
    };
    map.on("click", handler);
    map.getContainer().style.cursor = pickMode ? "crosshair" : "";
    return () => map.off("click", handler);
  }, [pickMode, onPickLocation]);

  // ── render incident markers ──
  useEffect(() => {
    const layer = markersLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    events.forEach((ev) => {
      const severity = ev.prediction?.severity;
      const isSelected = ev.id === selectedEventId;
      const marker = L.marker([ev.latitude, ev.longitude], {
        icon: buildIncidentIcon(severity, isSelected),
        zIndexOffset: isSelected ? 1000 : 0,
      });
      marker.on("click", () => onSelectEvent(ev.id));
      marker.bindTooltip(
        `<div class="vy-tooltip"><strong>${ev.event_cause.replaceAll("_", " ")}</strong><br/>${ev.corridor || "Non-corridor"}</div>`,
        { direction: "top", offset: [0, -10], className: "vy-tooltip-wrap" }
      );
      marker.addTo(layer);
    });
  }, [events, selectedEventId, onSelectEvent]);

  // ── render response-card overlay: barricade points + diversion routes ──
  useEffect(() => {
    const map = mapRef.current;
    const layer = overlayLayerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    if (!responseCard) return;

    const { event, barricade, diversion } = responseCard;

    // incident point, emphasized
    const incidentMarker = L.circleMarker([event.latitude, event.longitude], {
      radius: 9,
      color: "#ff9d2e",
      weight: 2,
      fillColor: "#ff9d2e",
      fillOpacity: 0.25,
    }).addTo(layer);
    incidentMarker.bindTooltip("Incident", { permanent: false, direction: "top" });

    // barricade points
    (barricade?.points || []).forEach((p) => {
      L.marker([p.latitude, p.longitude], {
        icon: L.divIcon({
          className: "vy-marker-wrap",
          html: `<span class="vy-barricade-icon" title="${p.label}">▲</span>`,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
      })
        .bindTooltip(`<div class="vy-tooltip"><strong>${p.label}</strong><br/>${p.instruction}</div>`, {
          direction: "top",
          className: "vy-tooltip-wrap",
        })
        .addTo(layer);
    });

    // diversion routes, ranked colors
    const ROUTE_COLORS = ["#23d18b", "#5ab8ff", "#c98bff"];
    (diversion?.routes || []).forEach((route, idx) => {
      const latlngs = route.coordinates.map(([lat, lon]) => [lat, lon]);
      L.polyline(latlngs, {
        color: ROUTE_COLORS[idx % ROUTE_COLORS.length],
        weight: idx === 0 ? 4 : 3,
        opacity: idx === 0 ? 0.95 : 0.6,
        dashArray: idx === 0 ? null : "6 6",
      })
        .bindTooltip(route.description, { sticky: true, className: "vy-tooltip-wrap" })
        .addTo(layer);
    });

    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.35), { animate: true, maxZoom: 16 });
    } else {
      map.flyTo([event.latitude, event.longitude], 15);
    }
  }, [responseCard]);

  // ── pan to a newly selected event from the list (no overlay yet) ──
  useEffect(() => {
    if (!mapRef.current || responseCard) return;
    const ev = events.find((e) => e.id === selectedEventId);
    if (ev) mapRef.current.flyTo([ev.latitude, ev.longitude], Math.max(mapRef.current.getZoom(), 14));
  }, [selectedEventId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="vy-map-stage">
      <div ref={mapElRef} className="vy-map-canvas" />
      {pickMode && (
        <div className="vy-map-pickhint">
          <span className="eyebrow">Click the map to place the incident</span>
        </div>
      )}
      <div className="vy-map-legend">
        <span className="severity-badge low">Low</span>
        <span className="severity-badge medium">Medium</span>
        <span className="severity-badge high">High</span>
      </div>
    </div>
  );
}
