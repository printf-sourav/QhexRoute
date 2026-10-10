import { ArrowRight, ChevronDown, Crosshair, FlaskConical, Play, RotateCcw, Settings2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { Coordinates, Preview, Scenario, Settings } from '../types';

export const presets = [
  { name: 'Central disruption', detail: 'A localized closure across Bengaluru fleet routes', latitude: 12.9716, longitude: 77.5946, severity: 3, resolution: 9 },
  { name: 'East junction', detail: 'A smaller incident affecting one central corridor', latitude: 12.971, longitude: 77.602, severity: 2, resolution: 9 },
  { name: 'Quiet corner', detail: 'Test an incident outside the central route graph', latitude: 13.125, longitude: 77.72, severity: 1, resolution: 10 },
  { name: 'District closure', detail: 'Stress test: some vehicles may have no route', latitude: 12.9716, longitude: 77.5946, severity: 5, resolution: 8 },
];
type Props = {
  settings: Settings; incident: Coordinates; scenario: Scenario; preview: Preview | null;
  busy: boolean; canRun: boolean; previewing: boolean; preset: string;
  onSettings: (next: Settings) => void; onIncident: (point: Coordinates) => void;
  onPreset: (name: string) => void; onRun: () => void; onReset: () => void;
};
export default function SetupPanel(p: Props) {
  const [coordinates, setCoordinates] = useState({ lat: String(p.incident.latitude), lon: String(p.incident.longitude) });
  useEffect(() => setCoordinates({ lat: p.incident.latitude.toFixed(5), lon: p.incident.longitude.toFixed(5) }), [p.incident]);
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => p.onSettings({ ...p.settings, [key]: value });
  const validCoordinates = Number.isFinite(Number(coordinates.lat)) && Number.isFinite(Number(coordinates.lon)) && coordinates.lat !== '' && coordinates.lon !== '' &&
    Number(coordinates.lat) >= p.scenario.bounds[0][1] && Number(coordinates.lat) <= p.scenario.bounds[1][1] && Number(coordinates.lon) >= p.scenario.bounds[0][0] && Number(coordinates.lon) <= p.scenario.bounds[1][0];
  return <aside className="setup-panel" aria-label="Experiment controls">
     <div className="panel-title"><span className="section-index">01</span><div><h2>Set up an incident</h2><p>Real roads. A testable decision.</p></div><Settings2 size={17} /></div>
    <fieldset disabled={p.busy}>
      <label className="field"><span>Test scenario <FlaskConical size={13} /></span><div className="select-wrap"><select aria-label="Test scenario" value={p.preset} onChange={e => p.onPreset(e.target.value)}>{presets.map(v => <option key={v.name}>{v.name}</option>)}<option value="Custom incident">Custom incident</option></select><ChevronDown size={14} /></div></label>
       <p className="field-hint">{presets.find(v => v.name === p.preset)?.detail ?? `Your own incident inside the ${p.scenario.city.name} study envelope.`}</p>
      <div className="field severity-field"><div className="field-label"><label htmlFor="severity">Closure severity</label><output htmlFor="severity">{p.settings.severity}<span> / 5</span></output></div><input id="severity" type="range" min="1" max="5" value={p.settings.severity} onChange={e => update('severity', Number(e.target.value))} /><div className="range-labels"><span>Minor</span><span>Widespread</span></div></div>
      <details className="coordinate-details"><summary><Crosshair size={13} />Incident coordinates <ChevronDown size={13} /></summary><div className="coordinate-fields"><label>Latitude<input aria-label="Incident latitude" type="number" step="0.00001" value={coordinates.lat} onChange={e => setCoordinates({ ...coordinates, lat: e.target.value })} /></label><label>Longitude<input aria-label="Incident longitude" type="number" step="0.00001" value={coordinates.lon} onChange={e => setCoordinates({ ...coordinates, lon: e.target.value })} /></label></div><button className="secondary-button compact" disabled={!validCoordinates} onClick={() => p.onIncident({ latitude: Number(coordinates.lat), longitude: Number(coordinates.lon) })}>Apply coordinates <ArrowRight size={13} /></button>{!validCoordinates && <p className="field-hint">Enter a point inside the Bengaluru study envelope.</p>}</details>
      <div className="field-row"><label className="field"><span>H3 resolution</span><select aria-label="H3 resolution" value={p.settings.resolution} onChange={e => update('resolution', Number(e.target.value))}><option value="8">8 · District</option><option value="9">9 · Street</option><option value="10">10 · Block</option></select></label><label className="field"><span>Route limit</span><select aria-label="Candidate routes" value={p.settings.candidates} onChange={e => update('candidates', Number(e.target.value))}><option value="2">2 / vehicle</option><option value="3">3 / vehicle</option></select></label></div>
      <div className="control-section"><span className="section-index">02</span><h2>Choose a solver</h2></div>
      <div className="solver-buttons" role="group" aria-label="Solver mode">{(['compare', 'classical', 'qaoa'] as const).map(v => <button key={v} aria-pressed={v === p.settings.solver} onClick={() => update('solver', v)}>{v === 'qaoa' ? 'QAOA' : v === 'classical' ? 'Classical' : 'Compare'}</button>)}</div>
      <p className="field-hint">{p.settings.solver === 'classical' ? 'Greedy baseline and exact reference.' : 'Same candidate instance for every solver. A classical result is used when QAOA is unavailable.'}</p>
      <details className="advanced-settings"><summary>Experiment parameters <ChevronDown size={13} /></summary><div className="field-row"><label className="field"><span>QAOA depth</span><select aria-label="QAOA depth" disabled={p.settings.solver === 'classical'} value={p.settings.depth} onChange={e => update('depth', Number(e.target.value))}><option value="1">p = 1</option><option value="2">p = 2</option></select></label><label className="field"><span>Shots</span><select aria-label="Shots" disabled={p.settings.solver === 'classical'} value={p.settings.shots} onChange={e => update('shots', Number(e.target.value))}>{[256, 512, 1024].map(n => <option key={n}>{n}</option>)}</select></label></div><label className="field"><span>Simulation seed</span><input type="number" aria-label="Simulation seed" min="0" max="999999" step="1" value={p.settings.seed} onChange={e => { const value = Number(e.target.value); if (Number.isInteger(value) && value >= 0 && value <= 999999) update('seed', value); }} /></label><p className="field-hint">Same seed + incident + settings reproduce routes and costs. Runtime can vary.</p></details>
        <div className="localization-preview" aria-live="polite"><span className="eyebrow">LOCALIZED SCOPE</span><div><strong>{p.previewing ? '…' : p.preview?.affected_vehicle_ids.length ?? '—'}<small> / {p.scenario.vehicles.length}</small></strong><span>vehicles impacted</span></div><p>{p.previewing ? 'Checking incident impact…' : p.preview ? `${p.preview.affected_region.cell_ids.length} route-local H3 cells · ${p.preview.affected_region.edge_count} OSM edges closed` : `${p.scenario.route_h3_coverage.cell_count.toLocaleString()} route H3 cells ready to explore.`}</p></div>
    </fieldset>
    <div className="setup-actions"><button className="primary-button" disabled={!p.canRun} onClick={p.onRun}><Play size={15} fill="currentColor" />{p.busy ? 'Running optimization…' : 'Run re-optimization'}<ArrowRight size={16} /></button>
      <button className="reset-button" disabled={p.busy} onClick={p.onReset}><RotateCcw size={13} />Reset experiment</button></div>
    <div className="setup-footnote">QAOA cap: <strong>12 variables</strong><span>Unavailable or oversized runs use a validated classical result.</span></div>
  </aside>;
}
