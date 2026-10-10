# Q-HexRoute agent instructions

- Treat this as a hackathon prototype with real end-to-end behavior, not a static mockup.
- The frontend uses React, TypeScript, and Vite. Astra referred to the coding model, not Astro; do not reintroduce Astro.
- Use Context7 before writing code against Qiskit, H3, OSMnx, FastAPI, NetworkX, or MapLibre APIs that may have changed.
- Use Playwright MCP after meaningful frontend slices and before declaring completion.
- Keep QAOA inputs at or below the configured variable cap; fall back to a feasible classical solution when necessary.
- Never fabricate optimization metrics or claim quantum advantage.
- Preserve deterministic seeds and compare solvers on identical instances.
- Run backend tests, frontend checks, production build, and the browser happy path before finalizing.
