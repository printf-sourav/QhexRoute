# Dashboard verification — 10 October 2026

Implemented React/TypeScript/Vite migration, a city-scale Bengaluru H3 coverage
layer plus local MapLibre routing context with an attributed OpenStreetMap
basemap and the Vite worker URL required by MapLibre 6, separate
incident-placement and inspection modes, complete-route fit, before/after
views, layer visibility, keyboard coordinates, vehicle candidates, repeatable
presets, abortable previews, invalidation of stale results and JSON export. The
backend now respects scenario seeds, generates a cached H3 fill of an
approximate Bengaluru urban envelope, keeps the central routing fixture
deterministic, removes closed roads before search, preserves the requested H3
resolution, reports unroutable vehicles, uses an objective-wide QUBO penalty
bound, exposes stable selection encode/decode helpers, and enforces a bounded
optional-QAOA worker.

## Checks

- `npm test`: 18 backend tests passed, including the 1,832-cell Bengaluru H3
  coverage response.
- `npm run check`: TypeScript check passed.
- `npm run build`: production build passed.
- `npm run test:browser`: 7 Chromium tests passed with the final code.
- Playwright browser verification: desktop/mobile screenshots, completed
  comparison, vehicle selection and console review; zero browser errors in the
  final comparison session. Headless Chromium emitted only four repeated
  OpenGL `ReadPixels` performance warnings from the container renderer; no app
  warnings or uncaught errors were recorded. The container required user-local
  Chromium runtime libraries because its system image does not provide them.
- Responsive checks: 1440×900, 1280×800, 1024×800, 768×1024, 390×844 and 320×740.
  No horizontal page overflow; Run stays in view on the laptop layouts.
- Regression strength: temporarily reinstating a false feasible result caused
  the unroutable-vehicle test to fail. The original implementation was restored
  and the test passed. The browser stress-case check also detects that defect.
- Frontend runtime dependency audit: zero reported vulnerabilities after the
  MapLibre 6.12.0 upgrade. The previous package was affected by
  [GHSA-jrc7-96c5-q579](https://github.com/advisories/GHSA-jrc7-96c5-q579).

## User paths exercised

Real default comparison and explicit QAOA fallback; all six before/after rows;
vehicle selection and candidate inspection; map layers; before/after views;
export download; severity and seed changes without map recreation; reset;
explicit map placement and incident dragging; quiet-corner no-change result;
district-closure partial result; mobile coordinate entry and controls; dialog
keyboard dismissal; recovery from a failed optimization request.

## Scope and limits

The H3 coverage is an approximate Bengaluru urban study envelope, not an
official administrative boundary or live city dataset. The routing graph is a
bounded cached OSMnx driving extract with simulated traffic weights, not a
complete Bengaluru traffic model. Optional QAOA circuit execution was not enabled; the tested path
explicitly uses classical fallback. No quantum advantage is claimed. MapLibre
6 requires WebGL2; unavailable map initialization leaves presets, coordinates
and the route table accessible. The production build reports a large MapLibre
chunk; the map loads separately from the main dashboard. Backend tests report
a Starlette/httpx deprecation warning, with all tests passing.

Screenshots: [ready](screenshots/dashboard-ready.png),
[completed run](screenshots/dashboard-result.png),
[mobile](screenshots/dashboard-mobile.png).
