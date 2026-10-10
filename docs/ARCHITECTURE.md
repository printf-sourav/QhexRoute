# Q-HexRoute architecture

Q-HexRoute is intentionally split into a React/TypeScript/Vite frontend and a local
FastAPI service.

## Frontend

`frontend/src/components/Dashboard.tsx` owns settings, incident placement and
API request state. SetupPanel, Inspector and RunResults render controls,
vehicle details and measured outputs. RouteMap is loaded separately and updates
GeoJSON sources in place; settings changes do not recreate the map. It has
explicit inspect/incident modes, full-route fit, layer controls and before/after
views. Abortable previews prevent stale responses from replacing the latest
incident. Changes to inputs invalidate the previous run. The map combines the
cached city-wide Bengaluru H3 coverage with an interactive OpenStreetMap raster
basemap. Synthetic routing geometry remains an explicitly labelled overlay;
the basemap requires network access and displays OSM attribution.

## Backend

`backend/app/main.py` loads the cached OSMnx directed driving graph in central
Bengaluru and normalizes its road geometry, lengths, and one-way connectivity
for NetworkX. Edges carry free-flow time, simulated congestion, and dynamic
travel time. A separate cached `polygon_to_cells` fill produces the city-scale
H3 context at resolution 8, while route H3 polygons are generated from actual
OSM route geometries. The selected seed rebuilds deterministic traffic weights
over the same OSM topology for scenario, preview and optimization requests. The
service localizes incidents with H3, generates legal alternatives with
`networkx.shortest_simple_paths`, normalizes route metrics, builds an
explainable QUBO, and solves the small assignment by greedy and exhaustive
reference methods.

The optional QAOA path is bounded at a configurable cap of at most 12 binary
variables and a configurable 15-second daemon-worker deadline. If Qiskit is not enabled, the variable cap
is exceeded, the worker times out, or a quantum sample cannot be validated, the
API returns the best feasible classical solution and records the fallback
reason. The QUBO variable order has explicit selection encode/decode helpers,
so validation uses the same mapping as the solver. No quantum metrics are
invented. Quantum objectives and executed qubit counts are absent when no
quantum sample was obtained.

Affected edges are removed before candidate search. Affected vehicles without
a legal alternative are returned in `unroutable_vehicle_ids` and the full run
is `partial` with `feasible=false`. An incident affecting no routes returns
`no_change`; the service does not invent affected vehicles. The QUBO penalty
exceeds a bound on all unconstrained route and cross-vehicle overlap costs.

## API flow

1. `GET /api/scenario?seed=42` loads the seeded OSM road network, current vehicle routes, route H3 coverage, and the city-scale Bengaluru H3 metadata.
2. `POST /api/incidents/preview` maps a click to H3 cells and affected routes.
3. `POST /api/optimize` creates candidates only for affected vehicles and
   returns selected routes, solver comparison, QUBO metadata, and timings.
4. `GET /api/runs/{run_id}` retrieves an in-memory completed run.
