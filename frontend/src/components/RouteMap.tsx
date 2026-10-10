import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, Map as LibreMap, Marker } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Crosshair, Focus, Layers, Minus, MousePointer2, Plus, X } from 'lucide-react';
import type { FeatureCollection, LineString } from 'geojson';
import type { Coordinates, Preview, Result, RouteData, Scenario } from '../types';
import 'maplibre-gl/dist/maplibre-gl.css';

// MapLibre 6 cannot infer its worker URL through a Vite bundle. The worker
// query keeps the worker and its shared module together in dev and production.
maplibregl.setWorkerUrl(workerUrl);

type Props = {
  scenario: Scenario; incident: Coordinates; preview: Preview | null; result: Result | null;
  vehicle: string | null; candidate: string | null; busy: boolean;
  resetKey?: number;
  onIncident: (point: Coordinates) => void; onVehicle: (id: string | null) => void;
};
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
const duration = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 400;
function lines(routes: RouteData[], vehicle: string | null): FeatureCollection<LineString> {
  return { type: 'FeatureCollection', features: routes.map(route => ({ type: 'Feature',
    properties: { vehicle: route.vehicle_id, route: route.route_id, focus: !vehicle || route.vehicle_id === vehicle }, geometry: route.geometry })) };
}
const OSM_TILE_URL = import.meta.env.VITE_OSM_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '© OpenStreetMap contributors';

export default function RouteMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LibreMap | null>(null);
  const incidentMarker = useRef<Marker | null>(null);
  const markers = useRef<Marker[]>([]);
  const latest = useRef(props); latest.current = props;
  const [ready, setReady] = useState(false);
  const [rendered, setRendered] = useState(false);
  const [mode, setMode] = useState<'inspect' | 'incident'>('inspect');
  const modeRef = useRef(mode); modeRef.current = mode;
  const [view, setView] = useState<'compare' | 'before' | 'after'>('compare');
  const [layerPanel, setLayerPanel] = useState(false);
  // The cached graph contains thousands of directed OSM edges. Keep that
  // diagnostic layer opt-in so it does not paint a dense white veil over the
  // raster basemap; the route and H3 layers remain visible by default.
  const [layers, setLayers] = useState({ osmBase: true, routeGrid: true, routingGraph: false, cells: true, candidates: true, closures: true });
  const [message, setMessage] = useState<string | null>(null);

  const fitDistrict = () => map.current?.fitBounds(latest.current.scenario.routing_bounds, { padding: 56, duration: duration() });
  useEffect(() => {
    if (!container.current) return;
    const initial = latest.current;
    let instance: LibreMap;
     try { instance = new maplibregl.Map({ container: container.current,
       style: { version: 8, sources: {
         'osm-tiles': { type: 'raster', tiles: [OSM_TILE_URL], tileSize: 256, minzoom: 0, maxzoom: 19, attribution: OSM_ATTRIBUTION },
       }, layers: [
         { id: 'osm-raster', type: 'raster', source: 'osm-tiles', paint: { 'raster-fade-duration': 0 } },
       ] },
       bounds: initial.scenario.routing_bounds, fitBoundsOptions: { padding: 56 },
        minZoom: 9, maxZoom: 18, maxBounds: initial.scenario.bounds,
       attributionControl: false, dragRotate: false, pitchWithRotate: false,
     }); } catch {
      setMessage('This browser cannot initialize the map. Use a browser with WebGL2 enabled. You can still test presets, coordinate entry and the route table.');
      return;
    }
    map.current = instance;
     instance.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-left');
     instance.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');
     instance.on('error', event => {
       if ((event as { sourceId?: string }).sourceId === 'osm-tiles') setMessage('The OpenStreetMap basemap could not load. Check network access; routing overlays remain available.');
       else if (event.error?.message) setMessage('The map could not render. Vehicle details and incident coordinates are available in the panels.');
     });
     instance.on('load', () => {
        instance.addSource('route-cells', { type: 'geojson', data: initial.scenario.route_h3_coverage.cells_geojson });
        instance.addLayer({ id: 'route-cells-fill', type: 'fill', source: 'route-cells', paint: { 'fill-color': '#b6d8c9', 'fill-opacity': .13 } });
        instance.addLayer({ id: 'route-cells-line', type: 'line', source: 'route-cells', paint: { 'line-color': '#2e8669', 'line-width': .9, 'line-opacity': .6 } });
       instance.addSource('roads', { type: 'geojson', data: initial.scenario.road_network });
       instance.addLayer({ id: 'road-casing', type: 'line', source: 'roads', layout: { visibility: 'none' }, paint: { 'line-color': '#36584d', 'line-width': 4, 'line-opacity': .24 } });
       instance.addLayer({ id: 'roads', type: 'line', source: 'roads', layout: { visibility: 'none' }, paint: { 'line-color': '#466f61', 'line-width': 1.5, 'line-opacity': .48 } });
      instance.addSource('cells', { type: 'geojson', data: empty });
      instance.addLayer({ id: 'cells-fill', type: 'fill', source: 'cells', paint: { 'fill-color': '#e9ae52', 'fill-opacity': .2 } });
      instance.addLayer({ id: 'cells-line', type: 'line', source: 'cells', paint: { 'line-color': '#b58026', 'line-width': 1.5, 'line-dasharray': [3, 2] } });
      instance.addSource('closures', { type: 'geojson', data: empty });
      instance.addLayer({ id: 'closures', type: 'line', source: 'closures', paint: { 'line-color': '#ce714b', 'line-width': 5, 'line-dasharray': [2, 2] } });
      for (const id of ['unchanged', 'before', 'candidates', 'after']) {
        instance.addSource(id, { type: 'geojson', data: empty });
        instance.addLayer({ id, type: 'line', source: id, layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': id === 'after' ? '#157864' : id === 'before' ? '#477c9c' : id === 'candidates' ? '#8866aa' : '#899b9b',
            'line-width': id === 'after' ? 5 : id === 'candidates' ? 2.5 : 3,
            'line-opacity': ['case', ['get', 'focus'], id === 'unchanged' ? .55 : .95, .13],
            ...(id === 'before' || id === 'candidates' ? { 'line-dasharray': [2, 2] } : {}) } });
      }
      instance.on('click', event => {
        const p = latest.current;
        if (p.busy) return;
        if (modeRef.current === 'incident') {
          const { lat, lng } = event.lngLat, [sw, ne] = p.scenario.bounds;
          if (lng < sw[0] || lng > ne[0] || lat < sw[1] || lat > ne[1]) { setMessage('Place the incident inside the modelled district.'); return; }
          p.onIncident({ latitude: lat, longitude: lng }); setMode('inspect'); setMessage(null); return;
        }
          const features = instance.queryRenderedFeatures([[event.point.x - 6, event.point.y - 6], [event.point.x + 6, event.point.y + 6]], { layers: ['after', 'before', 'unchanged', 'candidates', 'cells-fill', 'route-cells-fill'] });
         const routeFeature = features.find(feature => typeof feature.properties?.vehicle === 'string');
         if (routeFeature) { p.onVehicle(routeFeature.properties?.vehicle as string); return; }
         const cellFeature = features.find(feature => typeof feature.properties?.cell === 'string');
          if (cellFeature) {
            const coverage = p.result?.route_h3_coverage ?? p.scenario.route_h3_coverage;
            setMessage(`${p.scenario.city.name} route H3 r${coverage.resolution} cell · ${cellFeature.properties?.cell}`);
            return;
          }
         p.onVehicle(null);
      });
      const element = document.createElement('div'); element.className = 'incident-marker';
      element.setAttribute('role', 'img'); element.setAttribute('aria-label', 'Incident location, drag to move or use coordinate fields');
      element.innerHTML = '<span>!</span>';
      const marker = new maplibregl.Marker({ element, draggable: true }).setLngLat([initial.incident.longitude, initial.incident.latitude]).addTo(instance);
      marker.on('dragend', () => {
        const point = marker.getLngLat(), [sw, ne] = latest.current.scenario.bounds;
        latest.current.onIncident({ latitude: Math.min(ne[1], Math.max(sw[1], point.lat)), longitude: Math.min(ne[0], Math.max(sw[0], point.lng)) });
      }); incidentMarker.current = marker;
      element.setAttribute('aria-label', 'Incident location, drag to move or use coordinate fields');
      setReady(true);
      // The bundled style has no remote tile lifecycle to settle. The load
      // handler has already installed every source, layer, marker, and event
      // used by the dashboard, so readiness should not depend on an idle event
      // that a local style is not required to emit.
      setRendered(true);
    });
    let previousWidth = container.current.clientWidth;
    const resize = new ResizeObserver(entries => {
      instance.resize();
      const width = entries[0].contentRect.width;
      if (width !== previousWidth) {
        previousWidth = width;
        // Keep the district visible when a laptop layout becomes a narrow map.
        // User zoom and pan remain untouched when the panel only changes height.
         if (!latest.current.vehicle) instance.fitBounds(latest.current.scenario.routing_bounds, { padding: 56, duration: 0 });
      }
    }); resize.observe(container.current);
    return () => { resize.disconnect(); markers.current.forEach(m => m.remove()); incidentMarker.current?.remove(); instance.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const instance = map.current; if (!ready || !instance) return;
     const { scenario, result, preview, vehicle } = props;
     const update = (id: string, data: FeatureCollection) => (instance.getSource(id) as GeoJSONSource).setData(data);
      update('roads', scenario.road_network); update('route-cells', (result?.route_h3_coverage ?? scenario.route_h3_coverage).cells_geojson);
    update('cells', preview?.affected_region.cells_geojson ?? empty);
    const affected = new Set(preview?.affected_vehicle_ids ?? []);
    const originals = scenario.vehicles.map(v => v.current_route);
    update('before', lines(result?.current_routes ?? originals.filter(r => affected.has(r.vehicle_id)), vehicle));
    update('unchanged', lines(result?.unaffected_routes ?? originals.filter(r => !affected.has(r.vehicle_id)), vehicle));
    update('candidates', lines((result?.candidate_routes ?? []).filter(r => !r.selected && (!vehicle || r.vehicle_id === vehicle) && (!props.candidate || props.candidate === r.route_id)), vehicle));
     update('after', lines(result?.selected_routes ?? [], vehicle));
     update('closures', { ...scenario.road_network, features: scenario.road_network.features.filter(f => preview?.affected_edge_ids.includes(f.properties?.edge_id)) });
     markers.current.forEach(m => m.remove()); markers.current = [];
     const label = (text: string, point: [number, number], className: string) => {
       const el = document.createElement('span'); el.className = className; el.textContent = text;
       markers.current.push(new maplibregl.Marker({ element: el }).setLngLat(point).addTo(instance));
       el.setAttribute('aria-hidden', 'true');
     };
     scenario.vehicles.forEach(v => {
       const element = document.createElement('button'); element.type = 'button';
       element.className = `vehicle-marker ${v.id === vehicle ? 'selected' : ''} ${affected.has(v.id) ? 'affected' : ''}`;
       element.textContent = v.id.replace('V-', ''); element.title = v.label;
       element.style.pointerEvents = modeRef.current === 'incident' ? 'none' : 'auto';
       element.setAttribute('aria-label', `Inspect ${v.label}`); element.disabled = props.busy;
      element.addEventListener('click', e => { e.stopPropagation(); latest.current.onVehicle(v.id); });
      markers.current.push(new maplibregl.Marker({ element }).setLngLat(v.current_route.geometry.coordinates[0] as [number, number]).addTo(instance));
      element.setAttribute('aria-label', `Inspect ${v.label}`);
      if (v.id === vehicle) label('DESTINATION', v.current_route.geometry.coordinates.at(-1) as [number, number], 'destination-marker');
    });
  }, [ready, props.scenario, props.preview, props.result, props.vehicle, props.candidate, props.busy]);

  useEffect(() => { if (ready) { incidentMarker.current?.setLngLat([props.incident.longitude, props.incident.latitude]); incidentMarker.current?.setDraggable(!props.busy); } }, [ready, props.incident, props.busy]);
  useEffect(() => {
    if (!ready) return;
    fitDistrict(); setMode('inspect'); setView('compare'); setMessage(null);
       setLayers({ osmBase: true, routeGrid: true, routingGraph: false, cells: true, candidates: true, closures: true });
  }, [ready, props.resetKey]);
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    const visible = (id: string, show: boolean) => m.setLayoutProperty(id, 'visibility', show ? 'visible' : 'none');
      ['route-cells-fill', 'route-cells-line'].forEach(id => visible(id, layers.routeGrid));
      visible('osm-raster', layers.osmBase);
      ['road-casing', 'roads'].forEach(id => visible(id, layers.routingGraph));
    ['cells-fill', 'cells-line'].forEach(id => visible(id, layers.cells));
    visible('closures', layers.closures); visible('candidates', layers.candidates && view === 'compare');
    visible('before', view !== 'after' || !props.result); visible('after', view !== 'before');
     m.getCanvas().style.cursor = mode === 'incident' ? 'crosshair' : 'grab';
     markers.current.forEach(marker => {
       const element = marker.getElement();
       if (element.classList.contains('vehicle-marker')) element.style.pointerEvents = mode === 'incident' ? 'none' : 'auto';
     });
  }, [ready, layers, view, mode, props.result]);
  useEffect(() => {
    if (!ready || !props.vehicle || !map.current) return;
    const routes = [props.scenario.vehicles.find(v => v.id === props.vehicle)?.current_route, ...props.result?.candidate_routes.filter(r => r.vehicle_id === props.vehicle) ?? []].filter((r): r is RouteData => !!r);
    const coordinates = routes.flatMap(r => r.geometry.coordinates);
    if (coordinates.length) {
      const bounds = new maplibregl.LngLatBounds(); coordinates.forEach(c => bounds.extend(c as [number, number]));
      map.current.fitBounds(bounds, { padding: 75, maxZoom: 15, duration: duration() });
    }
  }, [ready, props.vehicle, props.result, props.scenario]);

  return <section className="map-shell" aria-label="Interactive district map">
    <div ref={container} className="map-canvas" data-testid="district-map" data-ready={rendered} data-basemap="openstreetmap" />
    <div className="map-toolbar">
      <div className="map-modes" role="group" aria-label="Map interaction">
        <button aria-pressed={mode === 'inspect'} onClick={() => setMode('inspect')}><MousePointer2 size={14} />Inspect</button>
        <button aria-pressed={mode === 'incident'} disabled={props.busy} onClick={() => setMode('incident')}><Crosshair size={14} />Place incident</button>
      </div>
      <button className="map-tool" aria-expanded={layerPanel} onClick={() => setLayerPanel(!layerPanel)}><Layers size={14} />Layers</button>
    </div>
      {layerPanel && <div className="layer-panel"><strong>Map layers</strong>{Object.entries(layers).map(([key, value]) => <label key={key}><input type="checkbox" checked={value} onChange={e => setLayers({ ...layers, [key]: e.target.checked })} />{{ osmBase: 'OpenStreetMap basemap', routeGrid: 'Route H3 cells', routingGraph: props.scenario.graph_source === 'openstreetmap' ? 'OSM routing graph' : 'Synthetic routing graph', cells: 'Incident H3 cells', candidates: 'Alternative routes', closures: 'Closed road segments' }[key as keyof typeof layers] ?? key}</label>)}</div>}
    <div className="map-tools"><button aria-label="Zoom in" onClick={() => map.current?.zoomIn()}><Plus size={16} /></button><button aria-label="Zoom out" onClick={() => map.current?.zoomOut()}><Minus size={16} /></button><button aria-label="Fit district" onClick={() => { props.onVehicle(null); fitDistrict(); }}><Focus size={16} /></button></div>
    <div className="north-mark" aria-hidden="true">N<span>↑</span></div>
      <div className="map-bottom"><div className="map-legend"><span><i className="key-line city-grid" />Route H3 cells</span><span><i className="key-line cells" />Incident H3</span><span><i className="key-line before" />Original</span><span><i className="key-line after" />Chosen</span><span><i className="key-line candidate" />Alternative</span><span><i className="key-line unchanged" />Unaffected</span></div>
      {props.result && <div className="map-views" role="group" aria-label="Route view">{(['before', 'compare', 'after'] as const).map(v => <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>{v === 'compare' ? 'Both' : v === 'before' ? 'Before' : 'After'}</button>)}</div>}
    </div>
       <div className="map-attribution"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">{OSM_ATTRIBUTION}</a><span> · {props.scenario.graph_source === 'openstreetmap' ? 'OSM routing graph' : 'Synthetic fallback graph'}</span></div>
     <div className={`map-instruction ${mode === 'incident' ? 'placing' : ''}`} role="status">{mode === 'incident' ? `Click inside the ${props.scenario.city.name} envelope to place an incident. Drag the marker to adjust.` : props.vehicle ? `${props.vehicle} selected · click empty space to clear` : 'Select a vehicle or H3 cell to inspect. Pan and scroll to explore.'}</div>
    {message && <div className="map-message" role="status">{message}<button aria-label="Dismiss map message" onClick={() => setMessage(null)}><X size={14} /></button></div>}
  </section>;
}
