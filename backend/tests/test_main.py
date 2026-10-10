from fastapi.testclient import TestClient
import networkx as nx
import time

import backend.app.main as api

from backend.app.main import (
    app,
    Incident,
    OptimizeRequest,
    ScenarioEngine,
    build_qubo,
    decode_selection,
    dominated,
    encode_selection,
    exact_solution,
    greedy_solution,
    normalize,
    qaoa_solution,
    qaoa_solution_with_timeout,
    Route,
)


client = TestClient(app)


def test_normalization_handles_constant_and_empty_inputs():
    assert normalize([]) == []
    assert normalize([4.0, 4.0]) == [0.0, 0.0]
    assert normalize([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]


def test_seed_reproduces_the_directed_fixture():
    first = ScenarioEngine(42)
    second = ScenarioEngine(42)
    assert list(first.graph.edges(data="dynamic_time_s")) == list(second.graph.edges(data="dynamic_time_s"))


def test_incident_localization_is_deterministic_and_scoped():
    engine = ScenarioEngine(42)
    incident = Incident()
    first = engine.localization(incident, 9, 42)
    second = engine.localization(incident, 9, 42)
    assert first["cells"]["ids"] == second["cells"]["ids"]
    assert first["affected_vehicle_ids"] == second["affected_vehicle_ids"]
    assert len(first["affected_vehicle_ids"]) < first["total_vehicles"]


def test_severity_expands_h3_localization_deterministically():
    engine = ScenarioEngine(42)
    minor = engine.localization(Incident(severity=1), 9, 42)
    severe = engine.localization(Incident(severity=5), 9, 42)
    assert len(severe["cells"]["ids"]) > len(minor["cells"]["ids"])
    assert severe["cells"]["ids"] == engine.localization(Incident(severity=5), 9, 42)["cells"]["ids"]


def test_exact_and_greedy_select_one_route_per_vehicle():
    engine = ScenarioEngine(42)
    incident = Incident()
    localized = engine.localization(incident, 9, 42)
    cell_set = set(localized["cells"]["ids"])
    candidates = {}
    for vehicle in engine.vehicles:
        if vehicle["id"] in localized["affected_vehicle_ids"]:
            routes = engine.candidate_routes(vehicle, incident, cell_set, set(localized["affected_edge_ids"]), 2)
            if routes:
                candidates[vehicle["id"]] = routes
    qubo = build_qubo(candidates)
    exact, exact_metrics = exact_solution(candidates)
    greedy, greedy_metrics = greedy_solution(candidates)
    assert qubo["penalty"] > 0
    assert len(exact) == len(candidates)
    assert len(greedy) == len(candidates)
    assert len({route.vehicle_id for route in exact}) == len(exact)
    assert exact_metrics["total"] <= greedy_metrics["total"] + 1e-9


def test_candidate_dominance_is_pareto_based():
    better = Route("V", "better", ("A", "B"), ("E1",), 100, 20, .1, .1, (), {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    worse = Route("V", "worse", ("A", "B"), ("E2",), 110, 21, .2, .2, (), {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    assert dominated(worse, better)
    assert not dominated(better, worse)


def test_qubo_variable_mapping_round_trips_a_valid_selection():
    engine = ScenarioEngine(42)
    localized = engine.localization(Incident(), 9, 42)
    candidates = {}
    for vehicle in engine.vehicles:
        if vehicle["id"] in localized["affected_vehicle_ids"]:
            routes = engine.candidate_routes(vehicle, Incident(), set(localized["cells"]["ids"]), set(localized["affected_edge_ids"]), 2)
            if routes:
                candidates[vehicle["id"]] = routes
    qubo = build_qubo(candidates)
    selected, _ = exact_solution(candidates)
    encoded = encode_selection(selected, qubo)
    decoded, feasible = decode_selection(encoded, candidates, qubo)
    assert feasible
    assert [(route.vehicle_id, route.route_id) for route in decoded] == [(route.vehicle_id, route.route_id) for route in selected]


def test_empty_greedy_assignment_is_safe():
    selected, metrics = greedy_solution({})
    assert selected == []
    assert metrics["total"] == 0.0


def test_qaoa_cap_returns_structured_fallback_without_importing_optional_stack():
    qubo = {"variables": [{"vehicle_id": f"V{i}", "route_id": f"R{i}"} for i in range(13)]}
    reason = qaoa_solution({}, qubo, OptimizeRequest(incident=Incident()))[-1]
    assert reason is not None
    assert "cap exceeded" in reason


def test_qaoa_deadline_returns_fallback_when_optional_worker_is_slow(monkeypatch):
    def slow_solver(*args, **kwargs):
        time.sleep(.08)
        return [], {"total": 0.0}, "", 1, None

    monkeypatch.setattr(api, "qaoa_solution", slow_solver)
    monkeypatch.setattr(api, "QAOA_TIMEOUT_SECONDS", .01)
    result = qaoa_solution_with_timeout({}, {"variables": []}, OptimizeRequest(incident=Incident()))
    assert result[0] is None
    assert result[-1] is not None
    assert "timed out" in result[-1]


def test_api_happy_path_and_parameter_validation():
    assert client.get("/api/health").json()["status"] == "ok"
    scenario = client.get("/api/scenario").json()
    assert len(scenario["vehicles"]) == 6
    preview = client.post(
        "/api/incidents/preview",
        json={"latitude": 12.9716, "longitude": 77.5946, "severity": 3, "seed": 42, "h3_resolution": 9},
    )
    assert preview.status_code == 200
    assert preview.json()["affected_region"]["cell_ids"]
    optimized = client.post(
        "/api/optimize",
        json={
            "incident": {"latitude": 12.9716, "longitude": 77.5946, "severity": 3},
            "h3_resolution": 9,
            "candidate_count": 2,
            "qaoa_depth": 1,
            "shots": 512,
            "seed": 42,
            "solver_mode": "compare",
        },
    )
    payload = optimized.json()
    assert optimized.status_code == 200
    assert payload["feasible"] is True
    assert payload["quantum"]["variables"] <= payload["quantum"]["cap"]
    assert scenario["city"]["name"] == "Bengaluru"
    assert scenario["h3_coverage"]["resolution"] == 8
    assert scenario["h3_coverage"]["cell_count"] == len(scenario["h3_coverage"]["cells_geojson"]["features"])
    assert scenario["h3_coverage"]["cell_count"] > 100
    assert client.post("/api/incidents/preview", json={"latitude": 0, "longitude": 0, "severity": 3}).status_code == 422
    assert client.post("/api/optimize", json={"incident": {}, "candidate_count": 4}).status_code == 422


def test_scenario_seed_changes_and_reproduces_route_metrics():
    first = client.get('/api/scenario?seed=42').json()
    changed = client.get('/api/scenario?seed=73').json()
    repeated = client.get('/api/scenario?seed=73').json()
    assert changed['seed'] == 73
    assert changed['road_network'] == repeated['road_network']
    assert changed['road_network'] != first['road_network']


def test_osm_fixture_drives_routes_and_route_h3_cells():
    scenario = client.get('/api/scenario?seed=42').json()
    assert scenario['graph_source'] == 'openstreetmap'
    assert len(scenario['road_network']['features']) > 1000
    assert scenario['route_h3_coverage']['cell_count'] > 0
    assert len(scenario['route_h3_coverage']['cells_geojson']['features']) == scenario['route_h3_coverage']['cell_count']
    assert all(route['current_route']['edge_ids'][0].startswith('osm-') for route in scenario['vehicles'])


def test_osm_edge_geometry_is_oriented_and_route_segments_join():
    graph = nx.DiGraph()
    graph.add_node("A", lon=77.59, lat=12.97)
    graph.add_node("B", lon=77.60, lat=12.98)
    reversed_geometry = [[77.60, 12.98], [77.595, 12.975], [77.59, 12.97]]
    assert api._geometry_coordinates(reversed_geometry, "A", "B", graph) == [
        [77.59, 12.97],
        [77.595, 12.975],
        [77.60, 12.98],
    ]

    engine = ScenarioEngine(42)
    for vehicle in engine.vehicles:
        route = engine.current_route(vehicle)
        route_coordinates = route.geometry["coordinates"]
        assert route_coordinates[0] == [engine.graph.nodes[route.path[0]]["lon"], engine.graph.nodes[route.path[0]]["lat"]]
        assert route_coordinates[-1] == [engine.graph.nodes[route.path[-1]]["lon"], engine.graph.nodes[route.path[-1]]["lat"]]
        cursor = 0
        for source, target in zip(route.path, route.path[1:]):
            segment = api._geometry_coordinates(engine.graph[source][target].get("geometry_coords"), source, target, engine.graph)
            assert route_coordinates[cursor:cursor + len(segment)] == segment
            cursor += len(segment) - 1
        assert cursor == len(route_coordinates) - 1


def test_route_h3_coverage_keeps_only_cells_intersecting_the_line():
    coordinates = [[77.59, 12.9716], [77.60, 12.9716]]
    cells = api.route_h3_cell_ids(coordinates, 10)
    line = api.LineString(coordinates)
    assert cells
    assert all(api._h3_cell_polygon(cell).intersects(line) for cell in cells)


def test_incident_localization_checks_the_full_edge_geometry():
    graph = nx.DiGraph()
    graph.add_node("A", lon=77.59, lat=12.9716)
    graph.add_node("B", lon=77.60, lat=12.9716)
    data = {"geometry_coords": [[77.59, 12.9716], [77.595, 12.9716], [77.60, 12.9716]]}
    graph.add_edge("A", "B", **data)
    incident = api.Incident(latitude=12.9716, longitude=77.595, severity=1)
    assert api._distance_m(incident.latitude, incident.longitude, graph.nodes["A"]["lat"], graph.nodes["A"]["lon"]) > 240
    assert api._distance_m(incident.latitude, incident.longitude, graph.nodes["B"]["lat"], graph.nodes["B"]["lon"]) > 240
    assert api.edge_near_incident(graph, "A", "B", incident, data)


def test_empty_incident_region_does_not_invent_affected_vehicles():
    engine = ScenarioEngine(42)
    localized = engine.localization(Incident(latitude=13.125, longitude=77.72, severity=1), 10, 42)
    assert localized['affected_vehicle_ids'] == []


def test_quiet_incident_returns_no_change_and_can_be_retrieved():
    payload = client.post('/api/optimize', json={'incident': {'latitude': 13.125, 'longitude': 77.72, 'severity': 1}, 'solver_mode': 'compare'}).json()
    assert payload['status'] == 'no_change'
    assert payload['solver_used'] == 'exact'
    assert client.get(f"/api/runs/{payload['run_id']}").json() == payload


def test_closed_roads_are_removed_before_candidate_search():
    engine = ScenarioEngine(42)
    vehicle = engine.vehicles[0]
    blocked = {edge['edge_id'] for a, b, edge in engine.graph.edges(data=True)
               if a == 'N00' and b == 'N01'}
    routes = engine.candidate_routes(vehicle, Incident(), set(), blocked, 2)
    assert routes
    assert all(not blocked.intersection(route.edge_ids) for route in routes)


def test_unroutable_affected_vehicle_is_reported(monkeypatch):
    monkeypatch.setattr(ScenarioEngine, 'candidate_routes', lambda *args, **kwargs: [])
    payload = client.post('/api/optimize', json={'incident': {}, 'solver_mode': 'classical'}).json()
    assert payload['feasible'] is False
    assert payload['status'] == 'partial'
    assert payload['unroutable_vehicle_ids']
    assert payload['quantum']['final_solution_feasible'] is False


def test_optimize_is_reproducible_and_retains_every_vehicle():
    request = {'incident': {}, 'solver_mode': 'classical', 'seed': 73}
    first = client.post('/api/optimize', json=request).json()
    second = client.post('/api/optimize', json=request).json()
    assert first['selected_routes'] == second['selected_routes']
    assert first['objective'] == second['objective']
    assert first['quantum']['qubits'] is None
    assert first['comparison']['qaoa_objective'] is None
    assert len(first['selected_routes']) + len(first['unroutable_vehicle_ids']) == first['localization']['affected_vehicles']
    assert len(first['unaffected_routes']) + len(first['current_routes']) == first['localization']['total_vehicles']


def test_result_route_h3_coverage_covers_every_visible_route_view():
    payload = client.post('/api/optimize', json={'incident': {}, 'solver_mode': 'classical'}).json()
    coverage = set(payload['route_h3_coverage']['cell_ids'])
    displayed_routes = payload['selected_routes'] + payload['unaffected_routes'] + payload['current_routes'] + payload['candidate_routes']
    assert displayed_routes
    assert all(set(api.route_h3_cell_ids(route['geometry']['coordinates'], payload['route_h3_coverage']['resolution'])) <= coverage for route in displayed_routes)


def test_qubo_penalty_dominates_all_unconstrained_costs():
    candidate_map = {}
    for index in range(6):
        vehicle = f'V{index}'
        candidate_map[vehicle] = [Route(vehicle, f'{vehicle}-R{choice}', ('A', 'B'), tuple(f'E{i}' for i in range(20)),
                                       100 + choice, 20 + choice, .1 * choice, .1 * choice, (),
                                       {'type': 'LineString', 'coordinates': [[0, 0], [1, 1]]}) for choice in range(2)]
    qubo = build_qubo(candidate_map)
    overlap = sum(value for key, value in qubo['quadratic'].items()
                  if key.split('|')[0].split(':')[0] != key.split('|')[1].split(':')[0])
    assert qubo['penalty'] > sum(qubo['route_costs'].values()) + overlap
