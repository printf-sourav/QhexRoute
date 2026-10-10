# Dashboard update

The screen's job is to let a first-time visitor test an incident and understand
which vehicles change. React with Vite replaces the accidental Astro choice.
Keep the existing dark cartographic palette, with larger readable controls,
a map that fills its panel, mint for chosen routes and amber for closures.
The map uses an interactive OpenStreetMap basemap with visible attribution,
real OSM road geometry, and route-derived H3 cells. Keep simulated traffic and
incident risk clearly labelled; do not present them as live OSM data.

Acceptance: explicit inspect/place modes, draggable incident, keyboard coordinate
entry, fit district and full-route focus, before/after views, real layer toggles,
vehicle/candidate inspection, repeatable presets, automatic previews, export,
responsive controls, recoverable errors, and truthful feasible/partial/no-change
results. Changing any experiment input invalidates the previous result.
Preview requests must abort stale responses. Controls lock during optimization.
All metrics come from the API; QAOA absent means no quantum objective or qubit
count is shown. User-facing status follows actual requests, without timer stages.

Verify type check, production build, backend regression tests and Playwright
happy paths including mobile, incident placement, selection, reset, settings,
fallback, no-impact and no-route cases. Inspect screenshots and console through
the configured Playwright MCP.
