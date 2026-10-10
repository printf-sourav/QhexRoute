import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, ChevronRight, Cpu, FlaskConical, Hexagon, Info, Menu, RefreshCw, Route, X } from 'lucide-react';
import SetupPanel, { presets } from './SetupPanel';
import Inspector from './Inspector';
import RunResults from './RunResults';
import { initialSettings, type Coordinates, type Preview, type Result, type Scenario, type Settings } from '../types';

const API = import.meta.env.VITE_API_BASE ?? '';
const RouteMap = lazy(() => import('./RouteMap'));
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `The service returned ${response.status}. Please retry.`);
  }
  return response.json();
}

export default function Dashboard() {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [health, setHealth] = useState({ online: false, quantum: false });
  const [scenarioLoading, setScenarioLoading] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [incident, setIncident] = useState<Coordinates>({ latitude: 12.9716, longitude: 77.5946 });
  const [settings, setSettings] = useState<Settings>(initialSettings);
  const [running, setRunning] = useState(false);
  const [comparisonOpen, setComparisonOpen] = useState(true);
  const [vehicle, setVehicle] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<string | null>(null);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [preset, setPreset] = useState('Central disruption');
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [previewRevision, setPreviewRevision] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setScenarioLoading(true); setResult(null); setPreview(null); setError(null);
    void Promise.all([
      request<Scenario>(`/api/scenario?seed=${settings.seed}`, { signal: controller.signal }),
      request<{ status: string; qiskit_ready: boolean }>('/api/health', { signal: controller.signal }),
    ]).then(([data, status]) => { if (controller.signal.aborted) return; setScenario(data); setHealth({ online: status.status === 'ok', quantum: status.qiskit_ready }); })
      .catch(e => { if (!controller.signal.aborted) { setHealth({ online: false, quantum: false }); setError(`Cannot connect to the routing service. Start the app with npm run dev, then retry. ${e.message}`); } })
      .finally(() => { if (!controller.signal.aborted) setScenarioLoading(false); });
    return () => controller.abort();
  }, [settings.seed, retry]);

  useEffect(() => {
    if (!scenario || scenarioLoading || scenario.seed !== settings.seed) return;
    const controller = new AbortController();
    setPreviewing(true); setPreview(null); setError(null);
    const timer = window.setTimeout(() => {
      void request<Preview>('/api/incidents/preview', { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...incident, severity: settings.severity, seed: settings.seed, h3_resolution: settings.resolution }) })
        .then(data => { if (!controller.signal.aborted) setPreview(data); })
        .catch(e => { if (!controller.signal.aborted) setError(`Incident preview failed. ${e.message}`); })
        .finally(() => { if (!controller.signal.aborted) setPreviewing(false); });
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [scenario, scenarioLoading, incident, settings.severity, settings.resolution, settings.seed, previewRevision]);

  const clearRun = () => { setResult(null); setCandidate(null); };
  const changeIncident = useCallback((point: Coordinates) => { setIncident(point); setResult(null); setCandidate(null); setPreset('Custom incident'); }, []);
  const selectVehicle = useCallback((id: string | null) => { setVehicle(id); setCandidate(null); }, []);
  const changeSettings = (next: Settings) => { setSettings(next); clearRun(); };
  const applyPreset = (name: string) => {
    setPreset(name); const p = presets.find(v => v.name === name); if (!p) return;
    setIncident({ latitude: p.latitude, longitude: p.longitude }); setSettings(s => ({ ...s, severity: p.severity, resolution: p.resolution }));
    clearRun(); setVehicle(null); setPreviewRevision(v => v + 1);
  };
  const reset = () => { setSettings(initialSettings); setIncident({ latitude: 12.9716, longitude: 77.5946 }); setPreset('Central disruption'); clearRun(); setVehicle(null); setError(null); setPreviewRevision(v => v + 1); };
  const run = async () => {
    if (running || previewing || !preview || !scenario || scenarioLoading) return;
    setRunning(true); setResult(null); setCandidate(null); setError(null); setControlsOpen(false);
    try {
      const data = await request<Result>('/api/optimize', { method: 'POST', signal: AbortSignal.timeout(120_000), headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident: { ...incident, severity: settings.severity }, h3_resolution: settings.resolution, candidate_count: settings.candidates, qaoa_depth: settings.depth, shots: settings.shots, seed: settings.seed, solver_mode: settings.solver }) });
      setResult(data); setComparisonOpen(true);
    } catch (e) { setError(`Optimization failed. ${e instanceof Error ? e.message : 'Retry the request.'}`); }
    finally { setRunning(false); }
  };
  const exportRun = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...result, experiment_settings: settings }, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `qhexroute-${result.run_id}.json`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const impacted = preview?.affected_vehicle_ids.length ?? 0;
  const canRun = health.online && !scenarioLoading && !running && !previewing && !!preview && !error;

  if (!scenario) return <main className="loading-shell"><Hexagon size={42} /><h1>Q-HexRoute</h1><p>{error ? 'The local routing service is unavailable.' : 'Preparing your routing lab…'}</p>{error && <><p className="loading-error" role="alert">{error}</p><button className="primary-button" onClick={() => setRetry(v => v + 1)}><RefreshCw size={15} />Retry connection</button></>}</main>;
  const routeCoverage = result?.route_h3_coverage ?? scenario.route_h3_coverage;
  const usingOsmGraph = scenario.graph_source === 'openstreetmap';
  return <div className="app-shell">
    <a className="skip-link" href="#district-workspace">Skip to routing workspace</a>
     <header className="topbar"><div className="brand"><div className="brand-mark"><Hexagon size={30} /><span>Q</span></div><div><strong>Q-HexRoute<span className="prototype-tag">LAB</span></strong><small>H3-localized hybrid routing</small></div></div><span className="header-location">{scenario.city.name} <ChevronRight size={12} /><strong>Incident response</strong></span><div className="header-actions"><span className={`health-status ${health.online ? 'online' : ''}`}><i />{health.online ? 'Backend healthy' : 'Backend offline'}</span><span className="seed-chip">SEED <strong>{settings.seed}</strong></span><button className="icon-button about-button" aria-label="About this experiment" onClick={() => dialog.current?.showModal()}><Info size={17} /></button><button className="mobile-menu" aria-label={controlsOpen ? 'Close controls' : 'Open controls'} aria-expanded={controlsOpen} aria-controls="experiment-controls" onClick={() => setControlsOpen(!controlsOpen)}>{controlsOpen ? <X size={19} /> : <Menu size={19} />}</button></div></header>
     <main>
        <div className="page-heading"><div><span className="eyebrow">THE ROUTING LAB / EXPERIMENT 01</span><h1>Real roads. A local decision.</h1><p>{usingOsmGraph ? 'Follow OpenStreetMap roads, map the route cells, then localize one disruption.' : 'Follow the fallback road graph, map the route cells, then localize one disruption.'}</p></div><button className="help-link" onClick={() => dialog.current?.showModal()}><FlaskConical size={15} />How this experiment works <ArrowRight size={14} /></button></div>
      {error && <div className="error-banner" role="alert"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setRetry(v => v + 1)}>Retry connection</button><button className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={14} /></button></div>}
      <div className="workspace" id="district-workspace">
         <div id="experiment-controls" className={`control-column ${controlsOpen ? 'open' : ''}`}><SetupPanel settings={settings} scenario={scenario} incident={incident} preview={preview} busy={running} canRun={canRun} previewing={previewing || scenarioLoading} preset={preset} onSettings={changeSettings} onIncident={changeIncident} onPreset={applyPreset} onRun={run} onReset={reset} /></div>
           <div className="map-column"><div className="scope-strip"><div><Hexagon size={16} /><span>Route H3 coverage<strong>{routeCoverage.cell_count.toLocaleString()}<small> cells · r{routeCoverage.resolution}</small></strong></span></div><div><Route size={16} /><span>Impacted vehicles<strong>{previewing ? '…' : impacted}<small> / {scenario.vehicles.length}</small></strong></span></div><div><Hexagon size={16} /><span>Incident impact<strong>{previewing ? '…' : preview?.affected_region.cell_ids.length ?? '—'}<small> H3 cells</small></strong></span></div><div><Cpu size={16} /><span>Decision variables<strong>{result ? result.quantum.variables : '—'}<small>{result ? ` / ${result.quantum.cap}` : ' after run'}</small></strong></span></div></div><Suspense fallback={<div className="map-shell map-loading" role="status">Preparing the district map…</div>}><RouteMap scenario={scenario} incident={incident} preview={preview} result={result} vehicle={vehicle} candidate={candidate} resetKey={previewRevision} busy={running || scenarioLoading} onIncident={changeIncident} onVehicle={selectVehicle} /></Suspense><div className="map-caption"><span><Check size={13} />OpenStreetMap basemap · route H3 cells · {usingOsmGraph ? 'OSM routing' : 'synthetic fallback'}</span><span className="quantum-state">QAOA {health.quantum ? 'enabled' : 'optional / off'}</span></div></div>
        <Inspector scenario={scenario} preview={preview} result={result} busy={running} previewing={previewing || scenarioLoading} vehicle={vehicle} candidate={candidate} onVehicle={selectVehicle} onCandidate={setCandidate} />
      </div>
      <RunResults result={result} scenario={scenario} open={comparisonOpen} onToggle={() => setComparisonOpen(!comparisonOpen)} onVehicle={selectVehicle} onExport={exportRun} />
      <footer className="page-footer"><span>Q-HexRoute <small>· Hybrid routing prototype</small></span><span>Simulated traffic. Measured results. No quantum advantage claimed.</span></footer>
    </main>
      <dialog ref={dialog} className="about-dialog"><form method="dialog"><button className="icon-button" aria-label="Close experiment information"><X size={18} /></button></form><span className="eyebrow">ABOUT THE EXPERIMENT</span><h2>Real roads.<br />Localized routing decisions.</h2><p>The map uses live OpenStreetMap raster tiles and {usingOsmGraph ? 'a cached OpenStreetMap driving graph' : 'a deterministic synthetic fallback graph'} for the routing overlay. H3 polygons are generated from the actual route geometries; the incident overlay shows the local H3 region.</p><ol><li><strong>Explore the road network.</strong> The route H3 layer follows {usingOsmGraph ? "the graph's OSM geometries instead of a generated city grid" : 'the fallback graph geometry'}.</li><li><strong>Place a disruption.</strong> Use a preset, the map's Place incident tool, or coordinate entry.</li><li><strong>Run the comparison.</strong> H3 cells and closed road segments identify affected vehicles. Greedy and exact solvers share the same candidates. Optional QAOA uses at most 12 variables, with an explicit classical fallback.</li><li><strong>Inspect and repeat.</strong> Select a vehicle, toggle Before / After and export the run. Same seed and inputs reproduce route metrics.</li></ol><p className="notice">Traffic congestion and incident risk remain simulated. This prototype demonstrates real road geometry and localized constrained assignment, not live traffic prediction, quantum speedup or production dispatch.</p></dialog>
  </div>;
}
