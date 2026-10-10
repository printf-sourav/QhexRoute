# 90-second demo

1. Start the app with `npm run dev` and open `http://localhost:4321`.
2. The dashboard fits the cached central Bengaluru OSM driving graph over real
   OpenStreetMap geography and renders H3 cells generated from the actual route
   geometries. The default **Central disruption** then previews affected
   vehicles at seed 42. Congestion and incident risk remain simulated.
3. Leave **Compare** selected and press **Run re-optimization**.
4. Walk through the run insight: city H3 coverage, local impact cells,
   feasibility, solver, normalized objective, decision variables and measured
   runtime.
5. Select Courier 104 in the fleet. Its full route and destination fit into
   view. Inspect original/chosen time, candidate distance and risk. Use
   **Before / Both / After**, then **Fit district**.
6. Show Greedy versus Exact and the QAOA path in **Compare the outcome**.
   On a standard install the optional quantum stack is deliberately off, so
   the UI should clearly say that a validated classical fallback was used.
7. Use **Place incident**, then click inside the Bengaluru envelope. Drag the amber
   marker to move it. Notice the old result clears as the preview updates.
8. Try **Quiet corner** and run: no current route changes. Try **District
   closure**: vehicles without a legal route are named in a partial result.
9. Use **Export run** to save the measured output and exact inputs.
10. Open **About this experiment** and close by explaining that this proves
    city-scale H3 context plus localized constrained assignment mechanics, not
    a complete Bengaluru traffic model or quantum advantage.
