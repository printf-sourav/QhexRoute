# Scientific limitations

- The road network is a bounded cached OSMnx driving extract, not a live
  city-wide OSM graph or traffic feed.
- Congestion and incident risk are deterministic simulation values.
- H3 is used for localization and visualization; it is not a traffic model.
- The exact reference is exhaustive and only suitable for the bounded demo
  instance.
- QAOA is optional and constrained to 12 binary variables. Missing Qiskit,
  oversized instances, or infeasible samples use a validated
  classical fallback.
- Standard tests exercise the classical solvers and explicit QAOA fallback.
  Actual optional quantum circuit execution remains environment-dependent. The
  optional simulator runs in a daemon worker with a configurable 15-second
  server-side deadline (`QHEXROUTE_QAOA_TIMEOUT_SECONDS`); timeout, dependency,
  cap, and validation failures use the measured classical result.
- No claim is made about quantum advantage, quantum speedup, reduced city-wide
  congestion, or production dispatch readiness.
- The basemap uses interactive OpenStreetMap raster tiles, subject to the OSM
  tile usage policy and network availability. The cached road extract can become
  stale until the explicit OSM refresh command is run.
