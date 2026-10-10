# Q-HexRoute — Detailed Prototype Build Prompt

## How to use this prompt

This specification is for a React, TypeScript and Vite frontend with a
Python/FastAPI optimization service. Astra referred to the coding model.
The earlier framework assumption was incorrect and has been removed.

The target is a working hackathon prototype. Quantum execution uses an
optional local simulator; IBM Quantum hardware remains outside the MVP.

---

# Build prompt

You are a senior full-stack engineer, geospatial developer, quantum-computing prototyper, product designer, and test engineer. Build a complete, polished, locally runnable hackathon prototype named:

**Q-HexRoute — H3-Localized Quantum-Assisted Dynamic Routing**

Do not stop after writing a plan or producing static mockups. Inspect the repository, create the application, run it, test it, fix errors, and leave the project in a demonstrably working state. If the repository already contains useful files, preserve them and adapt your work to the existing structure. Ask a question only if a missing decision makes implementation genuinely impossible; otherwise make the assumptions below and proceed.

## 1. Product objective

Build an interactive web application that demonstrates this defensible technical idea:

1. Load or reuse a compact urban road network.
2. Represent the area using H3 cells.
3. Simulate a road incident at a user-selected location.
4. Identify the affected H3 cells, road segments, routes, and vehicles.
5. Keep unaffected vehicles unchanged.
6. Generate a small set of legal candidate routes for each affected vehicle using classical graph algorithms.
7. Convert the local vehicle-to-route assignment problem into a QUBO.
8. Solve the same small instance with:
   - a deterministic classical baseline;
   - an exact solver when the instance is small enough; and
   - QAOA on a local Qiskit simulator.
9. Decode and validate the QAOA result classically.
10. Repair or reject infeasible samples and fall back to the classical solution when necessary.
11. Visualize the incident, affected H3 region, old routes, candidate routes, selected routes, optimization metrics, and before/after comparison.

The project is a **hybrid classical–quantum routing prototype**. It must never claim quantum advantage, quantum speedup, lower real-world congestion, or city-scale performance unless measured evidence produced by this application supports the claim.

## 2. Non-negotiable MVP scope

Implement the following in the first working version:

- React and Vite frontend with TypeScript.
- React components for the interactive dashboard.
- MapLibre GL JS interactive map.
- Python FastAPI backend.
- OSMnx and NetworkX road-graph processing.
- H3 event localization.
- Simulated traffic and incident data using deterministic seeds.
- K-shortest legal route candidates per affected vehicle.
- Vehicle-route QUBO with exactly-one-route constraints.
- Classical greedy baseline.
- Exact small-instance reference solution.
- QAOA using Qiskit on a local ideal simulator.
- Classical decoding, feasibility checking, and fallback.
- Incident-triggered local re-optimization.
- A comparison view using real outputs from the current run.
- Automated backend tests and at least one browser-level happy-path test.
- A clear README and a short demo script.

Explicitly defer these features:

- traffic-signal phase variables;
- route-signal interaction terms;
- custom XY or constraint-preserving mixers;
- noisy-device simulation;
- IBM Quantum hardware execution;
- GA, PSO, QPSO, and QACO;
- authentication, multi-tenancy, billing, or production dispatch;
- city-wide real-time traffic ingestion.

Do not build placeholder controls for deferred features that look functional. If they appear anywhere, label them clearly as “Phase 2” or “Not included in this prototype.”

## 3. Core scientific model

For every affected vehicle `v`, generate retained route candidates `r` and define:

```text
x(v,r) ∈ {0,1}
```

`x(v,r) = 1` means vehicle `v` selects route candidate `r`.

Use a normalized objective that is small enough to explain in the UI:

```text
route_cost(v,r)
  = 0.40 * normalized_travel_time
  + 0.20 * normalized_distance
  + 0.25 * normalized_congestion
  + 0.15 * normalized_incident_risk
```

Add a pairwise overlap or congestion interaction penalty when two selected routes share affected road segments:

```text
overlap_cost((v,r),(u,s)) * x(v,r) * x(u,s)
```

Enforce exactly one selected route per affected vehicle:

```text
P_route = A * Σv (Σr x(v,r) - 1)^2
```

The final QUBO should be explainable as:

```text
QUBO = route costs + route-overlap costs + exactly-one penalties
```

Requirements for the QUBO implementation:

- Normalize route metrics before applying weights.
- Pick penalty `A` programmatically so violating an exactly-one constraint is always more expensive than any plausible gain in the unconstrained objective.
- Keep a stable variable-to-vehicle-route mapping.
- Return the QUBO matrix or coefficient list in a serializable debug representation.
- Validate the selected assignment after solving.
- Recompute the final objective from the decoded route selection rather than trusting a solver-reported number blindly.
- Use identical route candidates, weights, and random seed for all solver comparisons.

## 4. Quantum execution rules

Use current, supported Qiskit APIs after consulting current documentation. A reasonable implementation is a `QuadraticProgram`, conversion to QUBO/Ising form, QAOA with a sampler primitive and a bounded classical optimizer, and `MinimumEigenOptimizer` for decoding. Use an exact Qiskit/Numpy eigensolver or deterministic exhaustive enumeration as the exact small-instance reference.

Hard limits for a dependable demo:

- Default to 3 affected vehicles with 2 route candidates each.
- Allow a maximum of 4 affected vehicles and 3 candidates each for QAOA.
- Cap the quantum path at 12 binary variables by default.
- Make the cap configurable but safe.
- Default QAOA depth to `p = 1`; optionally allow `p = 2` from the UI.
- Use a fixed seed, bounded optimizer iterations, and a finite shot count.
- Time-box QAOA execution.
- If the variable count exceeds the cap, the QAOA run errors, times out, produces no sample, or produces no feasible decoded assignment, use the best feasible classical solution.
- The API and UI must say which solver produced the returned result: `qaoa`, `qaoa_repaired`, `exact`, `greedy`, or `classical_fallback`.
- Never fabricate qubit count, depth, shots, runtime, objective, or feasibility.

Record at least:

- binary variable/qubit count;
- requested QAOA depth `p`;
- shot count;
- optimizer iteration limit;
- optimizer wall-clock time;
- raw best sampled bitstring when available;
- raw sample feasibility;
- final solution feasibility;
- whether repair or fallback was used;
- final objective value;
- exact/classical objective value on the same instance;
- optimality gap when an exact optimum is available.

## 5. Geospatial and routing behavior

### Road graph

- Operate on a deliberately small urban district, not an entire city.
- Support a cached local GraphML or GeoJSON fixture so the demo works without a live OSM download.
- Optionally provide a script or endpoint that refreshes the fixture from OpenStreetMap through OSMnx.
- Keep all graph edges directed and respect one-way constraints.
- Store or derive edge length, free-flow travel time, simulated congestion, dynamic travel time, and incident risk.
- Preserve OpenStreetMap attribution wherever map tiles or OSM-derived data are shown.

### H3 localization

- Use a configurable H3 resolution, with a sensible default such as 9.
- Convert the incident latitude/longitude to its H3 cell.
- Expand to a small grid disk based on incident severity.
- Include additional cells needed to retain route continuity.
- Select affected road segments by spatial intersection or endpoint membership.
- Select affected vehicles only when their current route intersects the affected region.
- Return H3 cells as GeoJSON polygons for the frontend.
- Report the number of vehicles and candidate decisions before and after localization.

### Candidate generation

- Use `networkx.shortest_simple_paths` or another supported K-shortest-path approach on the directed graph.
- Weight paths by dynamic travel time, not distance alone.
- Generate more paths than needed, then prune.
- Reject duplicate paths, invalid paths, incident-blocked paths, and clearly dominated paths.
- Retain a small `K`, default 2 and maximum 3 for the QAOA demo.
- For every candidate, calculate distance, estimated travel time, congestion exposure, incident risk, affected H3 cells, and shared-edge overlap.
- Convert routes to GeoJSON LineStrings for map rendering.

### Deterministic simulation

- Put all randomness behind a user-visible or configuration seed.
- Simulate congestion as bounded multipliers on selected edges.
- Simulate incident severity, affected radius, and blocked or penalized edges.
- Re-running the same scenario with the same seed must reproduce the same candidate set and metrics.

## 6. Backend API

Use Pydantic request/response models. Keep the API small and explicit.

### `GET /api/health`

Return service status, graph readiness, Qiskit readiness, and app version.

### `GET /api/scenario`

Return the default scenario:

- road-network GeoJSON;
- H3 resolution;
- vehicles and their current routes;
- allowed incident area or map bounds;
- current simulation seed.

### `POST /api/incidents/preview`

Input:

```json
{
  "latitude": 0.0,
  "longitude": 0.0,
  "severity": 3,
  "seed": 42
}
```

Return incident point, affected H3 polygons, affected edge IDs, affected vehicle IDs, and localization statistics without running optimization.

### `POST /api/optimize`

Input shape:

```json
{
  "incident": {
    "latitude": 0.0,
    "longitude": 0.0,
    "severity": 3
  },
  "h3_resolution": 9,
  "candidate_count": 2,
  "qaoa_depth": 1,
  "shots": 1024,
  "seed": 42,
  "solver_mode": "compare"
}
```

Supported `solver_mode` values:

- `classical`
- `qaoa`
- `compare`

Return a stable response shape similar to:

```json
{
  "run_id": "run_...",
  "status": "success",
  "solver_used": "qaoa",
  "fallback_reason": null,
  "feasible": true,
  "repaired": false,
  "incident": {},
  "affected_region": {
    "cells_geojson": {},
    "edge_count": 0,
    "vehicle_count": 0
  },
  "localization": {
    "total_vehicles": 0,
    "affected_vehicles": 0,
    "variables_without_localization": 0,
    "variables_with_localization": 0,
    "reduction_percent": 0.0
  },
  "selected_routes": [],
  "candidate_routes": [],
  "unaffected_routes": [],
  "objective": {
    "total": 0.0,
    "travel_time": 0.0,
    "distance": 0.0,
    "congestion": 0.0,
    "incident_risk": 0.0,
    "overlap": 0.0
  },
  "comparison": {
    "greedy_objective": 0.0,
    "exact_objective": 0.0,
    "qaoa_objective": 0.0,
    "optimality_gap_percent": 0.0
  },
  "quantum": {
    "attempted": true,
    "backend": "local_simulator",
    "variables": 0,
    "qubits": 0,
    "qaoa_depth": 1,
    "shots": 1024,
    "optimizer_iterations": 0,
    "circuit_depth": null,
    "two_qubit_gate_count": null,
    "best_bitstring": null
  },
  "timing_ms": {
    "localization": 0.0,
    "candidate_generation": 0.0,
    "qubo_build": 0.0,
    "classical": 0.0,
    "qaoa": 0.0,
    "total": 0.0
  }
}
```

Use `null` for a metric that cannot be measured. Never substitute a plausible-looking fake number.

### `GET /api/runs/{run_id}`

Return a previously completed run held in a simple in-memory or local JSON run store. A production database is unnecessary for this prototype.

## 7. Frontend experience

Build a serious, polished command-center experience rather than a generic admin template.

### Page structure

Use one primary dashboard page with these regions:

1. **Top bar**
   - Q-HexRoute wordmark.
   - Subtitle: “H3-localized hybrid routing lab.”
   - Backend health indicator.
   - Current seed.
   - A compact “About this experiment” action.

2. **Left control rail**
   - Scenario selector with one reliable demo scenario.
   - Incident severity control from 1 to 5.
   - H3 resolution control with a narrow safe range.
   - Candidate routes control: 2 or 3.
   - Solver mode: Compare, Classical, or QAOA.
   - QAOA depth: 1 or 2.
   - Shot count with safe presets.
   - Seed field.
   - Primary action: “Run local re-optimization.”
   - Secondary action: “Reset scenario.”
   - Explain when QAOA will fall back because of the variable cap.

3. **Main map**
   - Dominant area of the page.
   - Road network in subdued styling.
   - Vehicles as labeled markers.
   - Current routes in cool gray/cyan.
   - Incident as an amber/red pulsing marker.
   - Affected H3 cells as translucent amber hexagons.
   - Candidate routes as thin selectable lines.
   - Final selected routes as strong violet/teal lines.
   - Unaffected routes remain visually unchanged.
   - A legend that clearly distinguishes current, candidate, optimized, and unaffected routes.
   - Clicking a vehicle focuses its old route, candidates, and chosen route.

4. **Right insight panel**
   - Run state: Ready, Localizing, Building candidates, Building QUBO, Solving, Validating, Completed, or Fallback.
   - Feasibility badge.
   - Solver-used badge.
   - Objective value.
   - Affected vehicles.
   - Variables/qubits.
   - H3 reduction percentage.
   - Total runtime.
   - Compact objective breakdown.
   - A clear fallback explanation if fallback occurs.

5. **Bottom comparison drawer**
   - Before/after route table.
   - Greedy vs exact vs QAOA objective bars.
   - Timings by stage.
   - Per-vehicle selected route and delta in travel time.
   - Experiment metadata: seed, weights, `p`, shots, variables, feasibility, and repair status.
   - A small “What this proves / What this does not prove” section.

### Primary interaction flow

1. The app loads a ready scenario with several vehicles and their original routes.
2. The user clicks the map to place an incident or drags an existing incident marker.
3. The app previews affected H3 cells and affected vehicles.
4. The user adjusts safe experiment parameters.
5. The user runs local re-optimization.
6. The interface shows meaningful stage progress.
7. Selected routes animate into view after the backend returns.
8. The user can select a vehicle and compare old, candidate, and optimized routes.
9. The comparison drawer shows classical and QAOA results from the exact same local instance.

Do not simulate completion with a timer disconnected from the backend. Progress may be coarse, but it must reflect actual request state.

## 8. Visual design direction

Create a distinct “urban mobility research console” aesthetic:

- Dark charcoal/navy canvas, not pure black.
- Warm off-white primary text.
- Teal/cyan for baseline mobility data.
- Violet for quantum-selected routes and quantum metrics.
- Amber/red only for incidents, risk, and warnings.
- Fine grid texture or restrained cartographic linework, with no distracting decorative noise.
- Compact technical typography for metrics; readable sans serif for body text.
- Strong hierarchy, generous map area, and restrained card borders.
- Rounded corners should be subtle rather than bubbly.
- Avoid excessive gradients, glowing effects, oversized headings, generic glassmorphism, and meaningless charts.
- Use motion sparingly: route draw-in, status transitions, incident pulse, and panel expansion.

Accessibility requirements:

- Do not communicate state through color alone.
- Provide visible focus styles.
- Use semantic controls and labels.
- Ensure keyboard access to all controls and the comparison drawer.
- Provide text alternatives for map-only information in the vehicle and route tables.
- Respect reduced-motion preferences.
- Maintain readable contrast.

Responsive behavior:

- Optimize first for a laptop demo at 1440×900 and 1280×800.
- At tablet widths, place controls in a collapsible drawer and insights below the map.
- At mobile widths, provide a useful summary and parameter flow even if the full map comparison is simplified.

## 9. Suggested project structure

Use a simple monorepo with clear boundaries:

```text
q-hexroute/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── lib/
│   │   ├── pages/
│   │   ├── styles/
│   │   └── types/
│   ├── public/
│   ├── vite.config.ts
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── graph/
│   │   ├── h3_engine/
│   │   ├── routing/
│   │   ├── optimization/
│   │   ├── quantum/
│   │   ├── postprocess/
│   │   ├── simulation/
│   │   ├── schemas/
│   │   ├── config.py
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
├── data/
│   └── demo/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEMO_SCRIPT.md
│   └── SCIENTIFIC_LIMITATIONS.md
├── .env.example
├── .gitignore
├── AGENTS.md
├── README.md
└── package.json
```

Avoid creating abstractions that are not needed for this prototype. Prefer small functions and typed data models over deep inheritance or plugin systems.

## 10. Technology choices

### Frontend

- React with Vite and strict TypeScript.
- React only for the interactive map, controls, live run state, and comparison UI.
- MapLibre GL JS for the map.
- Native CSS, CSS modules, or a light utility setup; do not let a design framework dictate a generic look.
- Use a small accessible chart library only if it saves time; simple SVG or CSS bars are acceptable and often preferable.
- Use generated local icons or a lightweight icon library. Do not use emoji as interface icons.

### Backend

- Python 3.12 unless installed package compatibility requires 3.11.
- `uv` for Python dependency and lockfile management.
- FastAPI and Pydantic.
- OSMnx, NetworkX, H3, Shapely, NumPy, and SciPy.
- Qiskit, Qiskit Optimization, and Qiskit Aer only when needed by the selected current Qiskit API.
- Pytest for unit and API tests.

### Data and persistence

- Cached local demo graph and scenario fixtures.
- In-memory or JSON-file run storage.
- No PostgreSQL, Redis, message queue, or cloud infrastructure for the MVP.

## 11. Required tests

### Backend unit tests

Test at least:

- incident coordinates map to an H3 cell;
- severity expands the affected cell set deterministically;
- unaffected vehicles remain unchanged;
- candidate routes obey graph direction and avoid blocked edges;
- candidate pruning removes duplicates and dominated candidates;
- metric normalization handles constant and empty inputs safely;
- the exactly-one penalty produces a valid QUBO;
- variable mapping round-trips through encode/decode;
- the exact solution selects one route per vehicle;
- QAOA output is validated before use;
- infeasible or failed QAOA triggers repair or fallback;
- final objectives are recomputed after decoding or repair;
- the same seed reproduces the same scenario.

### API tests

Test:

- health endpoint;
- default scenario endpoint;
- incident preview;
- successful classical optimization;
- successful comparison mode on the small fixture;
- invalid coordinates and out-of-range parameters;
- QAOA cap fallback response;
- response schema contains no fabricated numeric placeholders.

### Frontend and browser test

At minimum, automate this happy path:

1. Open the dashboard.
2. Confirm the backend is healthy.
3. Place or move an incident.
4. Confirm affected H3 cells appear.
5. Run compare mode.
6. Confirm the completed state, feasible badge, solver used, real metrics, and selected routes.
7. Select a vehicle and confirm old and optimized route information is visible.

Also check the browser console for uncaught errors and verify the main page at laptop and mobile widths.

## 12. Reliability and safety

- Validate latitude, longitude, H3 resolution, severity, candidate count, depth, shots, and seed.
- Bound all expensive inputs.
- Add timeouts around QAOA.
- Return structured, user-readable errors.
- Keep secrets out of the repository.
- Do not require an IBM Quantum token.
- Cache or bundle all data necessary for the default demo.
- Make external map tiles and live OSM refresh optional rather than single points of failure.
- Log each optimization run with run ID, seed, parameters, solver path, feasibility, and timings.
- Avoid logging sensitive environment values.
- Add CORS only for the local frontend origin in development.

## 13. Performance targets

On a normal developer laptop after dependencies are installed:

- Default scenario page becomes usable within 3 seconds.
- Incident preview responds within 500 ms on the bundled fixture.
- Classical optimization completes within 2 seconds.
- Default compare run completes within 20 seconds if QAOA is available.
- A QAOA timeout results in a useful classical fallback rather than a failed demo.
- UI interactions remain responsive while a solve is running.

Treat these as targets, measure them, and document any machine-dependent variance.

## 14. Build and run commands

Create and verify commands equivalent to:

```text
# install all dependencies
npm install
npm run setup

# run frontend and backend together
npm run dev

# run all tests
npm test

# run frontend checks/build
npm run check
npm run build

# run backend tests directly
cd backend
uv run pytest

# run backend directly
uv run uvicorn app.main:app --reload --port 8000
```

It is acceptable to adapt the exact root scripts to the repository, but the final README must contain copy-pasteable Windows PowerShell and macOS/Linux commands.

## 15. Implementation sequence

Work in thin, verified slices:

1. Inspect the repository and record assumptions.
2. Scaffold React/Vite frontend and FastAPI backend.
3. Implement health endpoint and frontend health state.
4. Add the cached demo graph and deterministic scenario.
5. Render the road graph, vehicles, and original routes.
6. Implement incident placement and H3 preview.
7. Implement affected-vehicle detection.
8. Implement candidate generation and pruning.
9. Implement normalized route metrics.
10. Implement greedy and exact small-instance solvers.
11. Implement QUBO construction and tests.
12. Implement QAOA with current supported Qiskit APIs.
13. Implement decoding, feasibility validation, and fallback.
14. Wire the optimize API to the dashboard.
15. Add real comparison metrics and run details.
16. Refine visual design, accessibility, and responsive behavior.
17. Add browser tests and inspect console/network failures.
18. Run the full test/build suite and fix all failures.
19. Write the demo script and scientific limitations.

Do not build the entire UI against hardcoded final JSON and only later attempt the backend. Complete a real end-to-end vertical slice early, then expand it.

## 16. Definition of done

The prototype is complete only when all of these are true:

- A new developer can start it from the README.
- The default demo works without private credentials.
- A user can place an incident and see affected H3 cells.
- Only affected vehicles are re-optimized.
- Candidate routes come from the actual graph fixture.
- The local assignment is represented as a real QUBO.
- Classical and QAOA paths receive the exact same instance.
- The returned route selection is classically validated.
- Failed or oversized quantum runs visibly fall back to a feasible classical result.
- The UI shows actual values returned by the backend.
- The map clearly distinguishes incident, affected area, old routes, candidates, selected routes, and unaffected routes.
- The comparison view reports objective, feasibility, variables, reduction, and timing.
- No screen claims quantum advantage or city-scale readiness.
- Backend tests pass.
- Frontend checks and production build pass.
- The browser happy-path test passes.
- There are no uncaught browser-console errors in the demo flow.

## 17. Final response required from the coding agent

When finished, report:

1. What was built.
2. The project structure.
3. Exact install, run, test, and build commands.
4. Which parts are real and which are simulated.
5. The actual QAOA size cap and fallback behavior.
6. Test/build results.
7. Known limitations.
8. The 90-second demo flow.
9. Any environment variable or optional network requirement.

Do not describe unimplemented features as completed.

---

# MCP and plugin setup for Codex CLI

## Recommended minimal MCP set

Use only the MCPs that materially improve this build. Codex already has local shell and repository access, so duplicate filesystem or terminal MCPs are usually unnecessary.

### 1. Context7 — strongly recommended

Purpose: current, version-specific documentation for Qiskit, FastAPI, H3, OSMnx, NetworkX, MapLibre, and supporting libraries.

```powershell
codex mcp add context7 --url https://mcp.context7.com/mcp
```

Equivalent local stdio configuration if the remote endpoint is unavailable:

```toml
[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp@latest"]
```

### 2. Playwright MCP — essential for visual verification

Purpose: open the running app, exercise the complete demo, inspect accessibility/DOM state, capture console errors, and check responsive layouts.

```toml
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest", "--headless"]
```

Use headed mode instead of `--headless` while visually tuning the map if your environment supports it.

### 4. GitHub MCP or GitHub plugin — optional

Attach this only if the agent must create a repository, push commits, inspect issues, or open a pull request. It is not required to build and run the prototype locally. Grant the minimum repository permissions needed.

### 5. Fetch/web MCP — optional fallback

Use only if the CLI cannot browse official documentation and Context7 does not cover a needed library. Restrict it to official documentation domains when possible.

## MCPs not needed for this prototype

- PostgreSQL or database MCP: use JSON/in-memory storage.
- Docker/Kubernetes/cloud MCP: local processes are sufficient.
- Google Maps MCP: use MapLibre plus OSM-derived data.
- IBM Quantum MCP: use Qiskit SDK and local simulator; IBM access is a later experiment.
- Generic filesystem MCP: unnecessary when Codex already has scoped workspace access.
- Sequential-thinking or memory MCP: these add context overhead without providing project data or verification capability.

## Recommended Codex plugins/skill packs

If these are available in your Codex plugin directory, enable the equivalent capabilities:

- **GitHub** — only when remote repository or pull-request operations are part of the job.
- **Codex Security** — optional final pass for dependency, secret, and input-boundary review; it is not needed during initial scaffolding.
- **Frontend UI engineering** — layout, accessibility, responsive behavior, and component quality.
- **Browser testing with DevTools/Playwright** — real browser verification.
- **Test-driven development** — QUBO, route selection, validation, and fallback logic.
- **Debugging and error recovery** — Qiskit and geospatial dependency failures.
- **Security and hardening** — API bounds, CORS, secrets, and unsafe inputs.
- **Code review and quality** — final review after all tests pass.

Do not install the OpenAI Developers plugin for this project unless you add an OpenAI API feature; Q-HexRoute itself does not require the OpenAI API.

## Suggested `AGENTS.md` instructions

Add a short repository-level instruction file so the CLI uses the attached tools consistently:

```markdown
# Q-HexRoute agent instructions

- Treat this as a hackathon prototype with real end-to-end behavior, not a static mockup.
- Use React, TypeScript and Vite; Astra is the coding model.
- Use Context7 before writing code against Qiskit, Qiskit Optimization, H3, OSMnx, FastAPI, or MapLibre APIs that may have changed.
- Use Playwright MCP after each meaningful frontend slice and before declaring completion.
- Keep QAOA inputs at or below the configured variable cap; fall back to the classical solver when necessary.
- Never fabricate optimization metrics or claim quantum advantage.
- Preserve deterministic seeds and compare solvers on identical instances.
- Run backend tests, frontend checks, production build, and the browser happy path before finalizing.
```

## Verify attached MCPs

```powershell
codex mcp list
```

Keep the enabled set small. For this build, **Context7 + Playwright** is the best default combination.
