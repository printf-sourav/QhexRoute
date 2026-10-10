import { Check, ChevronDown, CircleAlert, Download, FlaskConical } from 'lucide-react';
import type { Result, Scenario } from '../types';
import { fmt, minutes, solverLabel } from '../types';

export default function RunResults({ result, scenario, open, onToggle, onVehicle, onExport }: { result: Result | null; scenario: Scenario; open: boolean; onToggle: () => void; onVehicle: (id: string) => void; onExport: () => void }) {
  if (!result) return <section className="results-empty"><FlaskConical size={18} /><div><h2>Your experiment results will appear here</h2><p>Place an incident, run the comparison, then inspect each route. Everything is computed by the local service.</p></div><span>REPEATABLE BY SEED</span></section>;
  const largest = Math.max(result.comparison.greedy_objective, result.comparison.exact_objective, result.comparison.qaoa_objective ?? 0, 0.001);
  const rows = [...result.current_routes, ...result.unaffected_routes];
  return <section className="results-section" aria-label="Experiment results">
    <div className="results-heading"><button className="results-toggle" aria-expanded={open} onClick={onToggle}><span className="section-index">04</span><h2>Compare the outcome</h2><span className={`result-badge ${result.feasible ? 'success' : 'warning'}`}>{result.feasible ? <Check size={12} /> : <CircleAlert size={12} />}{result.feasible ? 'Validated' : 'Partial result'}</span><ChevronDown size={16} className={open ? 'rotated' : ''} /></button><button className="secondary-button compact" onClick={onExport}><Download size={14} />Export run</button></div>
    {open && <div className="results-content">
      {result.fallback_reason && <p className="notice"><CircleAlert size={15} /><span><strong>Classical fallback.</strong> {result.fallback_reason} No QAOA objective or executed qubit count is reported.</span></p>}
      {result.unroutable_vehicle_ids.length > 0 && <p className="notice warning"><CircleAlert size={15} /><span><strong>No legal replacement for {result.unroutable_vehicle_ids.join(', ')}.</strong> The incident closes all generated alternatives. Try a smaller closure or a different location. These vehicles are excluded from the solved assignment, so the full fleet result is partial.</span></p>}
      {result.status === 'no_change' && <p className="notice"><Check size={15} />No current route intersects this incident. The fleet stays unchanged; no optimization decisions were needed.</p>}
      <div className="results-grid"><div className="solver-comparison"><h3>Solver comparison</h3><p>Same seed, candidates and weighted objective. Lower is better.</p>{[
        { label: 'Greedy baseline', value: result.comparison.greedy_objective, tone: 'gray' },
        { label: 'Exact reference', value: result.comparison.exact_objective, tone: 'mint' },
        { label: 'QAOA', value: result.comparison.qaoa_objective, tone: 'violet' },
      ].map(v => <div className="objective-row" key={v.label}><span>{v.label}</span><div className="objective-track"><i className={v.tone} style={{ width: `${v.value == null ? 0 : Math.max(0, v.value / largest * 100)}%` }} /></div><strong>{v.value == null ? 'Not run' : fmt(v.value, 3)}</strong></div>)}<div className="comparison-note"><span>Returned solver: <strong>{solverLabel(result.solver_used)}</strong></span><span>Gap to exact: <strong>{fmt(result.comparison.optimality_gap_percent)}%</strong></span></div></div>
      <div className="timings"><h3>Measured runtime</h3><p>Wall-clock timings for this request.</p>{Object.entries(result.timing_ms).map(([key, value]) => <div key={key}><span>{{localization:'H3 localization',candidate_generation:'Candidate generation',qubo_build:'QUBO construction',classical:'Classical solvers',qaoa:'Quantum / fallback check',total:'Total request'}[key]}</span><strong>{fmt(value, 2)} ms</strong></div>)}</div>
       <div className="experiment-record"><h3>Experiment record</h3><p>Inputs saved with the exported result.</p><dl><div><dt>Seed</dt><dd>{result.metadata.seed}</dd></div><div><dt>Variables</dt><dd>{result.quantum.variables} / {result.quantum.cap} cap</dd></div><div><dt>QAOA requested</dt><dd>p={result.quantum.qaoa_depth}, {result.quantum.shots} shots</dd></div><div><dt>Quantum execution</dt><dd>{result.quantum.attempted ? 'Attempted' : 'Not attempted'}</dd></div><div><dt>Executed qubits</dt><dd>{result.quantum.qubits ?? 'Not measured'}</dd></div><div><dt>Optimizer limit</dt><dd>{result.quantum.optimizer_iteration_limit} iterations</dd></div><div><dt>Timeout</dt><dd>{fmt(result.quantum.timeout_seconds, 1)} s</dd></div><div><dt>Repair</dt><dd>{result.repaired ? 'Used' : 'None'}</dd></div></dl><p className="record-weights">Weights: time .40 · distance .20 · congestion .25 · risk .15</p></div></div>
      <div className="table-heading"><h3>Before & after · all vehicles</h3><span>Original times are from before the closure. A detour can be longer.</span></div>
      <div className="route-table-wrap"><table><thead><tr><th>Vehicle</th><th>Response</th><th>Original time</th><th>Chosen time</th><th>Change</th><th>Distance</th></tr></thead><tbody>{rows.map(before => {
        const chosen = result.selected_routes.find(r => r.vehicle_id === before.vehicle_id);
        const unroutable = result.unroutable_vehicle_ids.includes(before.vehicle_id);
        const unchanged = result.unaffected_routes.some(r => r.vehicle_id === before.vehicle_id);
        const after = chosen ?? (unchanged ? before : null);
        const delta = after ? after.travel_time_s - before.travel_time_s : null;
        return <tr key={before.vehicle_id}><td><button className="table-vehicle" onClick={() => onVehicle(before.vehicle_id)}>{scenario.vehicles.find(v => v.id === before.vehicle_id)?.label ?? before.vehicle_id}<small>{before.vehicle_id}</small></button></td><td><span className={`table-state ${unroutable ? 'warning' : chosen ? 'success' : ''}`}>{unroutable ? 'No legal route' : chosen ? `Chosen ${chosen.route_id.split('-').at(-1)}` : 'Unchanged'}</span></td><td>{minutes(before.travel_time_s)}</td><td>{after ? minutes(after.travel_time_s) : '—'}</td><td>{delta == null ? '—' : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${minutes(Math.abs(delta))}`}</td><td>{after ? `${fmt(after.distance_m / 1000, 2)} km` : '—'}</td></tr>;
      })}</tbody></table></div>
       <div className="scientific-note"><FlaskConical size={15} /><p>This experiment demonstrates city-scale H3 context plus localized routing and constrained assignment on simulated data. The road graph is intentionally compact; this does not establish quantum advantage or real traffic improvement.</p><span className="run-id">{result.run_id}</span></div>
    </div>}
  </section>;
}
