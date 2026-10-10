import { ArrowUpRight, Check, CircleAlert, Route, X } from 'lucide-react';
import type { Preview, Result, Scenario } from '../types';
import { fmt, minutes, solverLabel } from '../types';

type Props = { scenario: Scenario; preview: Preview | null; result: Result | null; busy: boolean; previewing: boolean; vehicle: string | null; candidate: string | null; onVehicle: (id: string | null) => void; onCandidate: (id: string | null) => void };
export default function Inspector(p: Props) {
  const selected = p.scenario.vehicles.find(v => v.id === p.vehicle);
  const before = p.result?.current_routes.find(r => r.vehicle_id === p.vehicle) ?? selected?.current_route;
  const after = p.result?.selected_routes.find(r => r.vehicle_id === p.vehicle);
  const routes = p.result?.candidate_routes.filter(r => r.vehicle_id === p.vehicle) ?? [];
  const unroutable = p.result?.unroutable_vehicle_ids.includes(p.vehicle ?? '');
  const affected = p.preview?.affected_vehicle_ids.includes(p.vehicle ?? '');
  const state = p.busy ? 'Optimizing routes' : p.previewing ? 'Localizing incident' : p.result ? p.result.status === 'no_change' ? 'No routes affected' : p.result.feasible ? 'Completed with validation' : 'Partial · action required' : 'Ready to test';
  return <aside className="inspector" aria-label="Route and run insights">
    <div className="panel-title"><span className="section-index">03</span><div><h2>Inspect the response</h2><p>Every route has a reason.</p></div><Route size={17} /></div>
    <div className={`run-state ${p.busy || p.previewing ? 'busy' : ''}`} role="status"><span className="status-dot" /><div><strong>{state}</strong><small>{p.busy ? 'Waiting for the routing service' : p.result ? solverLabel(p.result.solver_used) : 'Preview the impact, then run a solver.'}</small></div></div>
    {p.result && <div className="run-summary"><div><span>Normalized objective</span><strong>{fmt(p.result.objective.total, 3)}</strong></div><div><span>Total runtime</span><strong>{fmt(p.result.timing_ms.total)} <small>ms</small></strong></div><span className={`result-badge ${p.result.feasible ? 'success' : 'warning'}`}>{p.result.feasible ? <Check size={12} /> : <CircleAlert size={12} />}{p.result.status === 'no_change' ? 'No reroute needed' : p.result.feasible ? 'All affected vehicles routed' : `${p.result.unroutable_vehicle_ids.length} vehicle(s) without a route`}</span></div>}
    <div className="fleet-heading"><h3>Vehicle fleet</h3><span>{p.scenario.vehicles.length} vehicles</span></div>
    <div className="vehicle-list">{p.scenario.vehicles.map(v => {
      const impacted = p.preview?.affected_vehicle_ids.includes(v.id);
      const missing = p.result?.unroutable_vehicle_ids.includes(v.id);
      return <button key={v.id} className={`vehicle-row ${v.id === p.vehicle ? 'selected' : ''}`} aria-pressed={v.id === p.vehicle} disabled={p.busy} onClick={() => p.onVehicle(v.id)}><span className={`vehicle-number ${impacted ? 'impacted' : ''}`}>{v.id.replace('V-', '')}</span><span className="vehicle-copy"><strong>{v.label}</strong><small>{v.class} · {minutes(v.current_route.travel_time_s)}</small></span><span className={`fleet-status ${missing ? 'blocked' : impacted ? 'impacted' : ''}`}>{missing ? 'No route' : impacted ? 'Affected' : 'Unchanged'}</span><ArrowUpRight size={13} /></button>;
    })}</div>
    {selected && before ? <div className="vehicle-detail" aria-label="Selected vehicle details"><div className="detail-heading"><div><span className="eyebrow">ROUTE INSPECTOR</span><h3>{selected.label}</h3></div><button className="icon-button" aria-label="Clear vehicle selection" onClick={() => p.onVehicle(null)}><X size={14} /></button></div>
      <div className="route-endpoints"><span><i />{selected.start}<small>Origin</small></span><span className="endpoint-line" /><span><i />{selected.end}<small>Destination</small></span></div>
      <div className="before-after"><div><span>Original</span><strong>{minutes(before.travel_time_s)}</strong><small>{fmt(before.distance_m / 1000, 2)} km</small></div><div><span>{after ? 'Chosen' : 'Status'}</span><strong>{after ? minutes(after.travel_time_s) : unroutable ? 'No legal route' : affected ? 'Awaiting run' : 'Unchanged'}</strong><small>{after ? `${fmt(after.distance_m / 1000, 2)} km` : 'Directed fixture'}</small></div></div>
      {after && <p className="route-delta">{after.travel_time_s - before.travel_time_s >= 0 ? '+' : '−'}{minutes(Math.abs(after.travel_time_s - before.travel_time_s))} versus the original route before the closure.</p>}
      {unroutable && <p className="notice warning">The closure disconnects this vehicle. Its old route is retained for inspection; no feasible replacement is claimed.</p>}
      {routes.length > 0 && <div className="candidate-list"><h4>Legal route candidates</h4><button className="text-button" onClick={() => p.onCandidate(null)}>Show all alternatives</button>{routes.map(r => <button className={`candidate-row ${r.route_id === p.candidate ? 'selected' : ''}`} key={r.route_id} aria-pressed={r.route_id === p.candidate} onClick={() => p.onCandidate(r.route_id)}><span><strong>{r.route_id.split('-').at(-1)}</strong><small>{r.selected ? 'Chosen route' : 'Alternative'}</small></span><span>{minutes(r.travel_time_s)}<small>{fmt(r.distance_m / 1000, 2)} km · risk {fmt(r.incident_risk, 2)}</small></span>{r.selected && <Check size={13} />}</button>)}</div>}
    </div> : <div className="inspector-empty"><MouseRoute /><strong>Follow a single vehicle</strong><p>Select a marker or a fleet row to see its original route, alternatives and destination.</p></div>}
  </aside>;
}
function MouseRoute() { return <div className="empty-route-icon"><Route size={22} /><ArrowUpRight size={13} /></div>; }
