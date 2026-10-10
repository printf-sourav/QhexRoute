import type { FeatureCollection, LineString, Polygon } from 'geojson';

export type Coordinates = { latitude: number; longitude: number };
export type CityInfo = { name: string; alias: string; region: string; coverage_label: string };
export type H3Coverage = { resolution: number; cell_count: number; cells_geojson: FeatureCollection<Polygon> };
export type RouteData = {
  vehicle_id: string; route_id: string; path: string[]; edge_ids: string[];
  distance_m: number; travel_time_s: number; congestion: number; incident_risk: number;
  affected_cells: string[]; geometry: LineString; selected?: boolean;
};
export type Vehicle = { id: string; label: string; start: string; end: string; class: string; current_route: RouteData };
export type Scenario = {
  road_network: FeatureCollection<LineString>; h3_resolution: number; vehicles: Vehicle[];
  bounds: [[number, number], [number, number]]; routing_bounds: [[number, number], [number, number]];
  incident: Coordinates & { severity: number };
  seed: number; attribution: string; graph_source: 'openstreetmap' | 'synthetic'; city: CityInfo; h3_coverage: H3Coverage; route_h3_coverage: H3Coverage;
};
export type Preview = {
  incident: Coordinates & { severity: number };
  affected_region: { cells_geojson: FeatureCollection<Polygon>; cell_ids: string[]; edge_count: number; vehicle_count: number };
  affected_edge_ids: string[]; affected_vehicle_ids: string[];
  localization: { total_vehicles: number; affected_vehicles: number; variables_without_localization: number; variables_with_localization: number };
};
export type Result = {
  run_id: string; status: string; solver_used: string; fallback_reason: string | null;
  feasible: boolean; repaired: boolean; unroutable_vehicle_ids: string[];
  incident: Coordinates & { severity: number }; affected_region: Preview['affected_region'];
  localization: Preview['localization'] & { reduction_percent: number };
  selected_routes: RouteData[]; candidate_routes: RouteData[]; unaffected_routes: RouteData[]; current_routes: RouteData[];
  road_network: FeatureCollection<LineString>; route_h3_coverage: H3Coverage;
  objective: { total: number; travel_time: number; distance: number; congestion: number; incident_risk: number; overlap: number };
  comparison: { greedy_objective: number; exact_objective: number; qaoa_objective: number | null; optimality_gap_percent: number };
  quantum: { attempted: boolean; backend: string; variables: number; qubits: number | null; qaoa_depth: number; shots: number; optimizer_iterations: number | null; optimizer_iteration_limit: number; timeout_seconds: number; circuit_depth: number | null; two_qubit_gate_count: number | null; best_bitstring: string | null; final_solution_feasible: boolean; repair_or_fallback: boolean; cap: number };
  timing_ms: { localization: number; candidate_generation: number; qubo_build: number; classical: number; qaoa: number; total: number };
  metadata: { seed: number; weights: Record<string, number>; candidate_count: number };
};
export type Settings = { severity: number; resolution: number; candidates: number; solver: 'compare' | 'classical' | 'qaoa'; depth: number; shots: number; seed: number };
export const initialSettings: Settings = { severity: 3, resolution: 9, candidates: 2, solver: 'compare', depth: 1, shots: 512, seed: 42 };
export const fmt = (value: number | null | undefined, digits = 1) => value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits);
export const minutes = (value: number) => `${fmt(value / 60)} min`;
export const solverLabel = (value: string) => ({ exact: 'Exact reference', greedy: 'Greedy', qaoa: 'QAOA', qaoa_repaired: 'Repaired QAOA', classical_fallback: 'Classical fallback' })[value] ?? value;
