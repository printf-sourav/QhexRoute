"""Q-HexRoute's deterministic local routing API.

The routing fixture deliberately stays small so a demo can explain every
decision, while the scenario also carries a city-scale H3 coverage layer for
Bengaluru. NetworkX performs the graph work and H3 localizes the incident.
Quantum dependencies are optional: when unavailable, the API returns the
validated classical solution and records the exact fallback reason.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import os
import queue
import random
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

try:
    import h3
except ImportError:  # pragma: no cover - requirements install h3 in normal use
    h3 = None

try:
    import osmnx as ox
except ImportError:  # pragma: no cover - optional OSM fixture loader
    ox = None

try:
    from shapely import wkt
    from shapely.geometry import LineString, Polygon
except ImportError:  # pragma: no cover - requirements install shapely in normal use
    wkt = None
    LineString = None
    Polygon = None


APP_VERSION = "0.1.0"
DEFAULT_SEED = 42
H3_RESOLUTION = 9
CITY_NAME = "Bengaluru"
CITY_ALIAS = "Bangalore"
CITY_REGION = "Karnataka, India"
CITY_H3_RESOLUTION = 8
# This is an intentionally transparent urban study envelope, not a claim to
# be an official administrative boundary. H3 fills it by cell centroid.
CITY_LON_MIN, CITY_LON_MAX = 77.41, 77.79
CITY_LAT_MIN, CITY_LAT_MAX = 12.79, 13.18
BENGALURU_BOUNDARY: tuple[tuple[float, float], ...] = (
    (13.18, 77.52),
    (13.16, 77.66),
    (13.08, 77.78),
    (12.95, 77.79),
    (12.82, 77.72),
    (12.79, 77.56),
    (12.83, 77.43),
    (12.98, 77.41),
    (13.10, 77.45),
)
# The decision graph is a compact, deterministic synthetic district placed in
# central Bengaluru. The city-wide H3 layer provides context without claiming
# that the small graph is a complete city road network.
ROUTING_LON_ORIGIN, ROUTING_LAT_ORIGIN = 77.58, 12.962
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OSM_GRAPH_PATH = PROJECT_ROOT / "data" / "demo" / "roads.graphml"
try:
    # Allow a smaller experiment-specific cap while keeping the prototype's
    # twelve-variable safety ceiling non-negotiable.
    QAOA_VARIABLE_CAP = max(1, min(12, int(os.getenv("QHEXROUTE_QAOA_VARIABLE_CAP", "12"))))
except ValueError:
    QAOA_VARIABLE_CAP = 12
QAOA_MAX_ITERATIONS = 80
try:
    QAOA_TIMEOUT_SECONDS = max(0.1, min(120.0, float(os.getenv("QHEXROUTE_QAOA_TIMEOUT_SECONDS", "15"))))
except ValueError:
    QAOA_TIMEOUT_SECONDS = 15.0
LON_MIN, LON_MAX = CITY_LON_MIN, CITY_LON_MAX
LAT_MIN, LAT_MAX = CITY_LAT_MIN, CITY_LAT_MAX
ORIGIN = (LON_MIN, LAT_MIN)
WEIGHTS = {
    "travel_time": 0.40,
    "distance": 0.20,
    "congestion": 0.25,
    "incident_risk": 0.15,
}


class Incident(BaseModel):
    latitude: float = Field(12.9716, ge=LAT_MIN, le=LAT_MAX)
    longitude: float = Field(77.5946, ge=LON_MIN, le=LON_MAX)
    severity: int = Field(3, ge=1, le=5)


class PreviewRequest(Incident):
    seed: int = Field(DEFAULT_SEED, ge=0, le=999999)
    h3_resolution: int = Field(H3_RESOLUTION, ge=7, le=10)


class OptimizeRequest(BaseModel):
    incident: Incident
    h3_resolution: int = Field(H3_RESOLUTION, ge=7, le=10)
    candidate_count: int = Field(2, ge=2, le=3)
    qaoa_depth: int = Field(1, ge=1, le=2)
    shots: int = Field(512, ge=128, le=2048)
    seed: int = Field(DEFAULT_SEED, ge=0, le=999999)
    solver_mode: Literal["classical", "qaoa", "compare"] = "compare"


@dataclass(frozen=True)
class Route:
    vehicle_id: str
    route_id: str
    path: tuple[str, ...]
    edge_ids: tuple[str, ...]
    distance_m: float
    travel_time_s: float
    congestion: float
    incident_risk: float
    affected_cells: tuple[str, ...]
    geometry: dict[str, Any]


class ScenarioEngine:
    """Owns the OSM-backed routing graph and deterministic scenario state."""

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self.seed = seed
        self.graph = self._build_graph(seed)
        self.vehicles = self._build_vehicles(self.graph)
        self.runs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _build_graph(seed: int) -> nx.DiGraph:
        if os.getenv("QHEXROUTE_USE_OSM_GRAPH", "1") != "0" and OSM_GRAPH_PATH.exists():
            try:
                return _load_osm_graph(OSM_GRAPH_PATH, seed)
            except Exception:
                # A checked-in fixture should never make the demo unbootable.
                # The response remains truthful because the scenario metadata
                # identifies the synthetic fallback graph.
                pass

        graph = nx.DiGraph()
        rng = random.Random(seed)
        cols, rows = 6, 5
        for row in range(rows):
            for col in range(cols):
                node = f"N{row}{col}"
                lon = ROUTING_LON_ORIGIN + col * 0.0052
                lat = ROUTING_LAT_ORIGIN + row * 0.0046
                graph.add_node(node, lon=lon, lat=lat)

        for row in range(rows):
            for col in range(cols):
                here = f"N{row}{col}"
                for d_row, d_col, prefix in ((0, 1, "E"), (1, 0, "S")):
                    next_row, next_col = row + d_row, col + d_col
                    if next_row >= rows or next_col >= cols:
                        continue
                    there = f"N{next_row}{next_col}"
                    a = graph.nodes[here]
                    b = graph.nodes[there]
                    distance = _distance_m(a["lat"], a["lon"], b["lat"], b["lon"])
                    for source, target, direction in ((here, there, "f"), (there, here, "r")):
                        edge_id = f"{prefix}{row}{col}-{direction}"
                        congestion = round(1.0 + rng.random() * 0.34, 3)
                        graph.add_edge(
                            source,
                            target,
                            edge_id=edge_id,
                            distance_m=round(distance, 1),
                            free_flow_s=round(distance / 12.5, 2),
                            congestion=congestion,
                            dynamic_time_s=round(distance / 12.5 * congestion, 2),
                        )
        graph.graph["source"] = "synthetic"
        return graph

    @staticmethod
    def _build_vehicles(graph: nx.DiGraph) -> list[dict[str, Any]]:
        if graph.graph.get("source") == "openstreetmap":
            return _build_osm_vehicles(graph)
        return [
            {"id": "V-104", "label": "Courier 104", "start": "N00", "end": "N44", "class": "delivery"},
            {"id": "V-216", "label": "Shuttle 216", "start": "N04", "end": "N40", "class": "transit"},
            {"id": "V-031", "label": "Taxi 031", "start": "N02", "end": "N42", "class": "service"},
            {"id": "V-442", "label": "Van 442", "start": "N20", "end": "N40", "class": "delivery"},
            {"id": "V-510", "label": "Shuttle 510", "start": "N40", "end": "N00", "class": "transit"},
            {"id": "V-608", "label": "Courier 608", "start": "N13", "end": "N14", "class": "delivery"},
        ]

    def current_route(self, vehicle: dict[str, Any], incident_cells: set[str] | None = None, resolution: int = H3_RESOLUTION) -> Route:
        path = nx.shortest_path(self.graph, vehicle["start"], vehicle["end"], weight="dynamic_time_s")
        return self._route_from_path(vehicle["id"], "current", path, incident_cells or set(), resolution)

    def _route_from_path(
        self, vehicle_id: str, route_id: str, path: Iterable[str], incident_cells: set[str], resolution: int = H3_RESOLUTION
    ) -> Route:
        node_path = tuple(path)
        edges = [self.graph[a][b] for a, b in zip(node_path, node_path[1:])]
        edge_ids = tuple(edge["edge_id"] for edge in edges)
        distance = sum(edge["distance_m"] for edge in edges)
        travel_time = sum(edge["dynamic_time_s"] for edge in edges)
        congestion = sum(edge["congestion"] - 1 for edge in edges) / max(len(edges), 1)
        coordinates: list[list[float]] = []
        for index, edge in enumerate(edges):
            segment = _geometry_coordinates(edge.get("geometry_coords"), node_path[index], node_path[index + 1], self.graph)
            coordinates.extend(segment if not coordinates else segment[1:])
        if not coordinates:
            coordinates = [[self.graph.nodes[node]["lon"], self.graph.nodes[node]["lat"]] for node in node_path]
        route_cells = tuple(sorted(route_h3_cell_ids(coordinates, resolution)))
        affected = tuple(sorted(set(route_cells).intersection(incident_cells)))
        risk = min(1.0, len(affected) / max(len(route_cells), 1) + (0.06 if affected else 0.01))
        geometry = {
            "type": "LineString",
            "coordinates": coordinates,
        }
        return Route(
            vehicle_id=vehicle_id,
            route_id=route_id,
            path=node_path,
            edge_ids=edge_ids,
            distance_m=round(distance, 1),
            travel_time_s=round(travel_time, 2),
            congestion=round(max(0.0, congestion), 4),
            incident_risk=round(risk, 4),
            affected_cells=affected,
            geometry=geometry,
        )

    def localization(self, incident: Incident, resolution: int, seed: int) -> dict[str, Any]:
        cells = h3_cells(incident.latitude, incident.longitude, incident.severity, resolution)
        cell_set = set(cells["ids"])
        affected_edges: set[str] = set()
        for source, target, data in self.graph.edges(data=True):
            source_cell = cell_for_node(self.graph.nodes[source], resolution)
            target_cell = cell_for_node(self.graph.nodes[target], resolution)
            if source_cell in cell_set or target_cell in cell_set or edge_near_incident(self.graph, source, target, incident, data):
                affected_edges.add(data["edge_id"])

        current = [self.current_route(vehicle, cell_set, resolution) for vehicle in self.vehicles]
        affected_vehicle_ids = [
            route.vehicle_id for route in current if set(route.edge_ids).intersection(affected_edges) or route.affected_cells
        ]
        return {
            "cells": cells,
            "affected_edge_ids": sorted(affected_edges),
            "current_routes": current,
            "affected_vehicle_ids": affected_vehicle_ids,
            "total_vehicles": len(self.vehicles),
            "seed": seed,
        }

    def candidate_routes(
        self,
        vehicle: dict[str, Any],
        incident: Incident,
        cell_set: set[str],
        blocked_edges: set[str],
        count: int,
        resolution: int = H3_RESOLUTION,
    ) -> list[Route]:
        candidates: list[Route] = []
        try:
            # Search the legal graph, rather than rejecting only the first few
            # paths through the closure and incorrectly declaring no alternative.
            legal_graph = self.graph.copy()
            legal_graph.remove_edges_from([(a, b) for a, b, edge in self.graph.edges(data=True)
                                          if edge['edge_id'] in blocked_edges])
            paths = nx.shortest_simple_paths(legal_graph, vehicle["start"], vehicle["end"], weight="dynamic_time_s")
            for path in itertools.islice(paths, 40):
                route = self._route_from_path(vehicle["id"], f"{vehicle['id']}-R{len(candidates) + 1}", path, cell_set, resolution)
                if set(route.edge_ids).intersection(blocked_edges):
                    continue
                if any(existing.edge_ids == route.edge_ids for existing in candidates):
                    continue
                route = Route(
                    **{**route.__dict__, "incident_risk": route_risk(route, incident, self.graph)}
                )
                if any(dominated(route, existing) for existing in candidates):
                    continue
                candidates = [existing for existing in candidates if not dominated(existing, route)]
                candidates.append(route)
                if len(candidates) >= count:
                    break
        except nx.NetworkXNoPath:
            return []
        return candidates


def _float_value(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _geometry_coordinates(value: Any, source: str, target: str, graph: nx.DiGraph) -> list[list[float]]:
    geometry = value
    if isinstance(geometry, str) and wkt is not None:
        try:
            geometry = wkt.loads(geometry)
        except Exception:
            geometry = None
    if geometry is not None and hasattr(geometry, "coords"):
        coordinates = [[float(point[0]), float(point[1])] for point in geometry.coords]
        if len(coordinates) >= 2:
            return _orient_geometry_coordinates(coordinates, source, target, graph)
    if isinstance(geometry, (list, tuple)) and len(geometry) >= 2:
        coordinates = [[float(point[0]), float(point[1])] for point in geometry]
        return _orient_geometry_coordinates(coordinates, source, target, graph)
    return [
        [float(graph.nodes[source]["lon"]), float(graph.nodes[source]["lat"])],
        [float(graph.nodes[target]["lon"]), float(graph.nodes[target]["lat"])],
    ]


def _orient_geometry_coordinates(
    coordinates: list[list[float]], source: str, target: str, graph: nx.DiGraph
) -> list[list[float]]:
    """Orient an OSM edge geometry from its directed source node to its target.

    GraphML geometry is normally written in edge direction, but that is not a
    contract we should assume when loading third-party extracts. Snapping the
    endpoints to the graph nodes also makes adjacent edge geometries join
    exactly when a route is serialized as one LineString.
    """
    if len(coordinates) < 2 or source not in graph or target not in graph:
        return coordinates

    source_point = [float(graph.nodes[source]["lon"]), float(graph.nodes[source]["lat"])]
    target_point = [float(graph.nodes[target]["lon"]), float(graph.nodes[target]["lat"])]
    direct_cost = _distance_m(
        source_point[1], source_point[0], coordinates[0][1], coordinates[0][0]
    ) + _distance_m(target_point[1], target_point[0], coordinates[-1][1], coordinates[-1][0])
    reverse_cost = _distance_m(
        source_point[1], source_point[0], coordinates[-1][1], coordinates[-1][0]
    ) + _distance_m(target_point[1], target_point[0], coordinates[0][1], coordinates[0][0])
    if reverse_cost < direct_cost:
        coordinates = list(reversed(coordinates))

    coordinates[0] = source_point
    coordinates[-1] = target_point
    return coordinates


@lru_cache(maxsize=8)
def _load_osm_graph(path: Path, seed: int) -> nx.DiGraph:
    if ox is not None:
        raw_graph = ox.load_graphml(path)
    else:  # pragma: no cover - exercised only when the optional loader is absent
        raw_graph = nx.read_graphml(path)

    graph = nx.DiGraph()
    for node, data in raw_graph.nodes(data=True):
        node_id = str(node)
        lon = _float_value(data.get("x", data.get("lon")))
        lat = _float_value(data.get("y", data.get("lat")))
        if lon is None or lat is None:
            continue
        graph.add_node(node_id, lon=lon, lat=lat)

    if raw_graph.is_multigraph():
        edges = raw_graph.edges(keys=True, data=True)
    else:
        edges = ((source, target, 0, data) for source, target, data in raw_graph.edges(data=True))

    rng = random.Random(seed)
    for source, target, key, data in sorted(edges, key=lambda item: (str(item[0]), str(item[1]), str(item[2]))):
        source_id, target_id = str(source), str(target)
        if source_id not in graph or target_id not in graph:
            continue
        distance = _float_value(data.get("length"), _distance_m(
            graph.nodes[source_id]["lat"], graph.nodes[source_id]["lon"],
            graph.nodes[target_id]["lat"], graph.nodes[target_id]["lon"],
        )) or 1.0
        existing = graph.get_edge_data(source_id, target_id)
        if existing is not None and existing["distance_m"] <= distance:
            continue
        free_flow = max(4.0, distance / 11.1)
        congestion = round(1.0 + rng.random() * 0.34, 3)
        graph.add_edge(
            source_id,
            target_id,
            edge_id=f"osm-{source_id}-{target_id}-{key}",
            osm_id=str(data.get("osmid", "")),
            distance_m=round(distance, 1),
            free_flow_s=round(free_flow, 2),
            congestion=congestion,
            dynamic_time_s=round(free_flow * congestion, 2),
            geometry_coords=_geometry_coordinates(data.get("geometry"), source_id, target_id, graph),
        )

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError(f"OSM fixture {path} did not contain a usable directed graph")
    graph.graph["source"] = "openstreetmap"
    graph.graph["fixture"] = str(path)
    return graph


def _build_osm_vehicles(graph: nx.DiGraph) -> list[dict[str, Any]]:
    anchors = [
        ("V-104", "Courier 104", "delivery", (12.958, 77.575), (12.986, 77.619)),
        ("V-216", "Shuttle 216", "transit", (12.991, 77.577), (12.950, 77.610)),
        ("V-031", "Taxi 031", "service", (12.967, 77.562), (12.989, 77.595)),
        ("V-442", "Van 442", "delivery", (12.971, 77.616), (12.945, 77.583)),
        ("V-510", "Shuttle 510", "transit", (12.945, 77.603), (12.992, 77.578)),
        ("V-608", "Courier 608", "delivery", (12.968, 77.590), (12.978, 77.606)),
    ]
    components = sorted(nx.strongly_connected_components(graph), key=len, reverse=True)
    candidate_nodes = set(components[0]) if components and len(components[0]) >= 12 else set(graph.nodes)
    if not candidate_nodes:
        raise ValueError("OSM graph has no candidate vehicle nodes")

    def distance_to(node: str, point: tuple[float, float]) -> float:
        return _distance_m(point[0], point[1], graph.nodes[node]["lat"], graph.nodes[node]["lon"])

    def choose_pair(start_point: tuple[float, float], end_point: tuple[float, float]) -> tuple[str, str]:
        starts = sorted(candidate_nodes, key=lambda node: distance_to(node, start_point))[:32]
        ends = sorted(candidate_nodes, key=lambda node: distance_to(node, end_point))[:32]
        for start in starts:
            for end in ends:
                if start != end and nx.has_path(graph, start, end):
                    return start, end
        raise ValueError("OSM graph could not provide a connected vehicle pair")

    vehicles = []
    for vehicle_id, label, vehicle_class, start_point, end_point in anchors:
        start, end = choose_pair(start_point, end_point)
        vehicles.append({"id": vehicle_id, "label": label, "start": start, "end": end, "class": vehicle_class})
    return vehicles


def _distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    x = math.radians(lon_b - lon_a) * 6371000 * math.cos(math.radians((lat_a + lat_b) / 2))
    y = math.radians(lat_b - lat_a) * 6371000
    return math.hypot(x, y)


def cell_for_node(node: dict[str, float], resolution: int) -> str:
    if h3 is not None:
        return h3.latlng_to_cell(node["lat"], node["lon"], resolution)
    return f"fallback-{round(node['lat'], 3)}-{round(node['lon'], 3)}"


def h3_cells(latitude: float, longitude: float, severity: int, resolution: int) -> dict[str, Any]:
    if h3 is None:
        center = f"fallback-{round(latitude, 3)}-{round(longitude, 3)}"
        return {"ids": [center], "geojson": {"type": "FeatureCollection", "features": []}}
    center = h3.latlng_to_cell(latitude, longitude, resolution)
    # Keep the localization window compact for the demo. A higher severity is
    # still reflected in edge risk and the incident marker, while the default
    # run stays within a small assignment instance.
    radius = max(1, min(2, math.ceil(severity / 3)))
    ids = sorted(h3.grid_disk(center, radius))
    features = []
    for cell in ids:
        boundary = h3.cell_to_boundary(cell)
        coords = [[lon, lat] for lat, lon in boundary]
        coords.append(coords[0])
        features.append({"type": "Feature", "properties": {"cell": cell}, "geometry": {"type": "Polygon", "coordinates": [coords]}})
    return {"center": center, "ids": ids, "geojson": {"type": "FeatureCollection", "features": features}}


def _h3_edge_length_m(resolution: int) -> float:
    if h3 is None:
        return 80.0
    try:
        return float(h3.average_hexagon_edge_length(resolution, unit="m"))
    except (AttributeError, TypeError, ValueError):  # pragma: no cover - older h3 fallback
        return 80.0


def _route_h3_candidate_cell_ids(coordinates: list[list[float]], resolution: int) -> set[str]:
    """Find a bounded set of H3 cells near a route before exact intersection.

    Samples are deliberately spaced below one half of the average H3 edge
    length. A radius-two disk around each sample prevents a long diagonal edge
    from hiding a crossed cell; polygon intersection below removes those
    conservative candidates.
    """
    if h3 is None or not coordinates:
        return set()

    spacing_m = max(5.0, min(120.0, _h3_edge_length_m(resolution) * 0.35))
    candidates: set[str] = set()
    for first, second in zip(coordinates, coordinates[1:]):
        distance = _distance_m(first[1], first[0], second[1], second[0])
        steps = max(1, math.ceil(distance / spacing_m))
        for index in range(steps + 1):
            fraction = index / steps
            longitude = first[0] + (second[0] - first[0]) * fraction
            latitude = first[1] + (second[1] - first[1]) * fraction
            sample_cell = h3.latlng_to_cell(latitude, longitude, resolution)
            candidates.update(h3.grid_disk(sample_cell, 2))
    if len(coordinates) == 1:
        candidates.add(h3.latlng_to_cell(coordinates[0][1], coordinates[0][0], resolution))
    return candidates


def _h3_cell_polygon(cell: str) -> Any:
    if h3 is None or Polygon is None:
        return None
    boundary = h3.cell_to_boundary(cell)
    coordinates = [(float(lon), float(lat)) for lat, lon in boundary]
    coordinates.append(coordinates[0])
    return Polygon(coordinates)


def route_h3_cell_ids(coordinates: list[list[float]], resolution: int) -> set[str]:
    if h3 is None or not coordinates:
        return set()
    candidates = _route_h3_candidate_cell_ids(coordinates, resolution)
    if len(coordinates) < 2 or not candidates or LineString is None or Polygon is None:
        return candidates

    try:
        route_line = LineString([(float(point[0]), float(point[1])) for point in coordinates])
    except (TypeError, ValueError):  # pragma: no cover - defensive geometry fallback
        return candidates
    cells: set[str] = set()
    for cell in candidates:
        polygon = _h3_cell_polygon(cell)
        if polygon is not None and polygon.intersects(route_line):
            cells.add(cell)
    # Keep the route visible even if a future H3/Shapely combination rejects a
    # degenerate geometry during polygon construction.
    return cells or {
        h3.latlng_to_cell(float(point[1]), float(point[0]), resolution)
        for point in coordinates
    }


def route_h3_coverage(routes: Iterable[Route], resolution: int) -> dict[str, Any]:
    ids: set[str] = set()
    for route in routes:
        ids.update(route_h3_cell_ids(route.geometry.get("coordinates", []), resolution))
    features = []
    if h3 is not None:
        for cell in sorted(ids):
            boundary = h3.cell_to_boundary(cell)
            coords = [[lon, lat] for lat, lon in boundary]
            coords.append(coords[0])
            features.append({
                "type": "Feature",
                "properties": {"cell": cell, "resolution": resolution, "coverage": "route"},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            })
    return {
        "resolution": resolution,
        "cell_count": len(ids),
        "cell_ids": sorted(ids),
        "cells_geojson": {"type": "FeatureCollection", "features": features},
    }


@lru_cache(maxsize=4)
def city_h3_coverage(resolution: int = CITY_H3_RESOLUTION) -> dict[str, Any]:
    """Return a cached H3 centroid fill for the Bengaluru study envelope.

    The local incident overlay intentionally uses the requested experiment
    resolution. This separate, coarser layer makes the full city footprint
    visible without expanding the routing assignment or QAOA problem.
    """
    empty = {"type": "FeatureCollection", "features": []}
    if h3 is None:
        return {"resolution": resolution, "cell_count": 0, "cell_ids": [], "cells_geojson": empty}

    shape = h3.LatLngPoly(BENGALURU_BOUNDARY)
    to_cells = getattr(h3, "polygon_to_cells", None) or getattr(h3, "h3shape_to_cells")
    ids = sorted(to_cells(shape, resolution))
    features = []
    for cell in ids:
        boundary = h3.cell_to_boundary(cell)
        coords = [[lon, lat] for lat, lon in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "properties": {"cell": cell, "resolution": resolution, "coverage": "Bengaluru"},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    return {
        "resolution": resolution,
        "cell_count": len(ids),
        "cell_ids": ids,
        "cells_geojson": {"type": "FeatureCollection", "features": features},
    }


def _point_to_segment_distance_m(
    latitude: float, longitude: float, first: list[float], second: list[float]
) -> float:
    """Return a local-metric point-to-segment distance for lon/lat points."""
    x_scale = 111320.0 * math.cos(math.radians(latitude))
    y_scale = 110574.0
    px, py = longitude * x_scale, latitude * y_scale
    ax, ay = first[0] * x_scale, first[1] * y_scale
    bx, by = second[0] * x_scale, second[1] * y_scale
    dx, dy = bx - ax, by - ay
    if math.isclose(dx, 0.0) and math.isclose(dy, 0.0):
        return math.hypot(px - ax, py - ay)
    fraction = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    fraction = max(0.0, min(1.0, fraction))
    closest_x, closest_y = ax + fraction * dx, ay + fraction * dy
    return math.hypot(px - closest_x, py - closest_y)


def _geometry_distance_to_point_m(coordinates: list[list[float]], latitude: float, longitude: float) -> float:
    if len(coordinates) == 1:
        return _distance_m(latitude, longitude, coordinates[0][1], coordinates[0][0])
    return min(
        _point_to_segment_distance_m(latitude, longitude, first, second)
        for first, second in zip(coordinates, coordinates[1:])
    )


def edge_near_incident(
    graph: nx.DiGraph,
    source: str,
    target: str,
    incident: Incident,
    data: dict[str, Any] | None = None,
) -> bool:
    threshold_m = 170 + incident.severity * 70
    edge_data = data if data is not None else graph[source][target]
    coordinates = _geometry_coordinates(edge_data.get("geometry_coords"), source, target, graph)
    return _geometry_distance_to_point_m(coordinates, incident.latitude, incident.longitude) < threshold_m


def route_risk(route: Route, incident: Incident, graph: nx.DiGraph) -> float:
    risk = route.incident_risk
    for node in route.path:
        distance = _distance_m(incident.latitude, incident.longitude, graph.nodes[node]["lat"], graph.nodes[node]["lon"])
        risk += max(0, incident.severity * 0.012 - distance / 18000)
    return round(min(1.0, risk), 4)


def dominated(route: Route, other: Route) -> bool:
    return (
        other.distance_m <= route.distance_m
        and other.travel_time_s <= route.travel_time_s
        and other.congestion <= route.congestion
        and other.incident_risk <= route.incident_risk
        and (
            other.distance_m < route.distance_m
            or other.travel_time_s < route.travel_time_s
            or other.congestion < route.congestion
            or other.incident_risk < route.incident_risk
        )
    )


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def route_costs(routes: list[Route]) -> list[float]:
    tt = normalize([route.travel_time_s for route in routes])
    dist = normalize([route.distance_m for route in routes])
    cong = normalize([route.congestion for route in routes])
    risk = normalize([route.incident_risk for route in routes])
    return [
        WEIGHTS["travel_time"] * tt[index]
        + WEIGHTS["distance"] * dist[index]
        + WEIGHTS["congestion"] * cong[index]
        + WEIGHTS["incident_risk"] * risk[index]
        for index in range(len(routes))
    ]


def build_qubo(candidate_map: dict[str, list[Route]]) -> dict[str, Any]:
    all_routes = [route for routes in candidate_map.values() for route in routes]
    costs = route_costs(all_routes)
    overlap_bound = sum(0.035 * len(set(a.edge_ids).intersection(b.edge_ids))
                        for a, b in itertools.combinations(all_routes, 2) if a.vehicle_id != b.vehicle_id)
    penalty = math.ceil(sum(costs) + overlap_bound) + 1.0
    variables = []
    linear: dict[str, float] = {}
    quadratic: dict[str, float] = {}
    route_cost_by_key: dict[str, float] = {}
    cursor = 0
    for vehicle_id, routes in candidate_map.items():
        for route in routes:
            key = f"{vehicle_id}:{route.route_id}"
            variables.append({"index": cursor, "vehicle_id": vehicle_id, "route_id": route.route_id})
            route_cost_by_key[key] = round(costs[cursor], 5)
            linear[key] = round(costs[cursor] - penalty, 5)
            cursor += 1
        for first, second in itertools.combinations(routes, 2):
            quadratic[f"{vehicle_id}:{first.route_id}|{vehicle_id}:{second.route_id}"] = round(2 * penalty, 5)
    for (vehicle_a, routes_a), (vehicle_b, routes_b) in itertools.combinations(candidate_map.items(), 2):
        for route_a in routes_a:
            for route_b in routes_b:
                shared = len(set(route_a.edge_ids).intersection(route_b.edge_ids))
                if shared:
                    key_a = f"{vehicle_a}:{route_a.route_id}"
                    key_b = f"{vehicle_b}:{route_b.route_id}"
                    quadratic[f"{key_a}|{key_b}"] = round(0.035 * shared, 5)
    return {"variables": variables, "linear": linear, "quadratic": quadratic, "penalty": penalty, "route_costs": route_cost_by_key}


def route_variable_key(route: Route) -> str:
    """Return the stable QUBO variable name for one vehicle-route choice."""
    return f"{route.vehicle_id}:{route.route_id}"


def encode_selection(selection: list[Route], qubo: dict[str, Any]) -> str:
    """Encode a route selection using the QUBO variable ordering."""
    selected_keys = {route_variable_key(route) for route in selection}
    return "".join("1" if variable["vehicle_id"] + ":" + variable["route_id"] in selected_keys else "0" for variable in qubo["variables"])


def decode_selection(
    bitstring: str, candidate_map: dict[str, list[Route]], qubo: dict[str, Any]
) -> tuple[list[Route], bool]:
    """Decode and validate one assignment against the candidate map."""
    variables = qubo["variables"]
    if len(bitstring) != len(variables) or any(bit not in "01" for bit in bitstring):
        return [], False
    route_lookup = {
        route_variable_key(route): route
        for routes in candidate_map.values()
        for route in routes
    }
    selected = [
        route_lookup[key]
        for key, bit in zip(
            (variable["vehicle_id"] + ":" + variable["route_id"] for variable in variables), bitstring
        )
        if bit == "1" and key in route_lookup
    ]
    selected_by_vehicle = {route.vehicle_id for route in selected}
    feasible = (
        len(selected) == len(candidate_map)
        and len(selected_by_vehicle) == len(candidate_map)
        and selected_by_vehicle == set(candidate_map)
    )
    return selected, feasible


def score_selection(selection: list[Route], all_routes: list[Route], penalty: float) -> dict[str, float]:
    costs = route_costs(all_routes)
    cost_by_id = {route.route_id + ":" + route.vehicle_id: costs[index] for index, route in enumerate(all_routes)}
    route_cost = sum(cost_by_id[route.route_id + ":" + route.vehicle_id] for route in selection)
    overlap = 0.0
    for first, second in itertools.combinations(selection, 2):
        overlap += 0.035 * len(set(first.edge_ids).intersection(second.edge_ids))
    return {"route_cost": route_cost, "overlap": overlap, "total": route_cost + overlap}


def exact_solution(candidate_map: dict[str, list[Route]]) -> tuple[list[Route], dict[str, float]]:
    vehicle_ids = list(candidate_map)
    if not vehicle_ids or any(not candidate_map[vehicle_id] for vehicle_id in vehicle_ids):
        return [], {"route_cost": 0.0, "overlap": 0.0, "total": 0.0}
    all_routes = [route for routes in candidate_map.values() for route in routes]
    penalty = build_qubo(candidate_map)["penalty"]
    best_selection: list[Route] | None = None
    best_score: dict[str, float] | None = None
    for choices in itertools.product(*(candidate_map[vehicle_id] for vehicle_id in vehicle_ids)):
        selection = list(choices)
        score = score_selection(selection, all_routes, penalty)
        if best_score is None or score["total"] < best_score["total"]:
            best_selection, best_score = selection, score
    return best_selection or [], best_score or {"route_cost": 0.0, "overlap": 0.0, "total": 0.0}


def greedy_solution(candidate_map: dict[str, list[Route]]) -> tuple[list[Route], dict[str, float]]:
    if not candidate_map or any(not routes for routes in candidate_map.values()):
        return [], {"route_cost": 0.0, "overlap": 0.0, "total": 0.0}
    selected: list[Route] = []
    all_routes = [route for routes in candidate_map.values() for route in routes]
    route_cost = route_costs(all_routes)
    cost_by_key = {route.vehicle_id + ":" + route.route_id: route_cost[index] for index, route in enumerate(all_routes)}
    for routes in candidate_map.values():
        selected.append(min(routes, key=lambda route: cost_by_key[route.vehicle_id + ":" + route.route_id]))
    return selected, score_selection(selected, all_routes, build_qubo(candidate_map)["penalty"])


def qaoa_solution(
    candidate_map: dict[str, list[Route]], qubo: dict[str, Any], request: OptimizeRequest
) -> tuple[list[Route] | None, dict[str, float] | None, str | None, int | None, str | None]:
    """Run bounded QAOA when the optional current Qiskit stack is enabled.

    Imports stay inside this function so the default prototype remains usable
    on a lightweight Python install. Any API/version/runtime issue is returned
    as structured fallback information instead of being hidden.
    """
    if len(qubo["variables"]) > QAOA_VARIABLE_CAP:
        return None, None, None, None, f"QAOA cap exceeded: {len(qubo['variables'])} variables > {QAOA_VARIABLE_CAP} variable safety limit."
    try:
        from qiskit.primitives import StatevectorSampler
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA
        from qiskit_optimization import QuadraticProgram
        from qiskit_optimization.algorithms import MinimumEigenOptimizer

        program = QuadraticProgram()
        variable_names = [variable["vehicle_id"] + ":" + variable["route_id"] for variable in qubo["variables"]]
        for name in variable_names:
            program.binary_var(name=name)
        quadratic: dict[tuple[str, str], float] = {}
        for serialized_key, coefficient in qubo["quadratic"].items():
            left, right = serialized_key.split("|", 1)
            quadratic[(left, right)] = coefficient
        program.minimize(linear=qubo["linear"], quadratic=quadratic)
        try:
            sampler = StatevectorSampler(default_shots=request.shots, seed=request.seed)
        except TypeError:
            sampler = StatevectorSampler()
        evaluation_count = 0

        def record_evaluation(*_: Any) -> None:
            nonlocal evaluation_count
            evaluation_count += 1

        optimizer = COBYLA(maxiter=QAOA_MAX_ITERATIONS)
        qaoa = QAOA(sampler=sampler, optimizer=optimizer, reps=request.qaoa_depth, callback=record_evaluation)
        result = MinimumEigenOptimizer(qaoa).solve(program)
        bits = [int(round(float(value))) for value in result.x]
        bitstring = "".join(str(bit) for bit in bits)
        selected, feasible = decode_selection(bitstring, candidate_map, qubo)
        if not feasible:
            return None, None, "".join(str(bit) for bit in bits), evaluation_count, "QAOA produced an infeasible assignment; classical validation rejected the sample."
        metrics = score_selection(selected, [route for routes in candidate_map.values() for route in routes], qubo["penalty"])
        return selected, metrics, bitstring, evaluation_count, None
    except Exception as exc:  # pragma: no cover - depends on optional Qiskit versions
        return None, None, None, locals().get("evaluation_count", 0), f"QAOA unavailable or failed: {type(exc).__name__}: {exc}"


def qaoa_solution_with_timeout(
    candidate_map: dict[str, list[Route]], qubo: dict[str, Any], request: OptimizeRequest
) -> tuple[list[Route] | None, dict[str, float] | None, str | None, int | None, str | None]:
    """Run QAOA in a daemon worker so a slow optional dependency cannot hold the API."""
    result_queue: queue.Queue[tuple[list[Route] | None, dict[str, float] | None, str | None, int | None, str | None]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put(qaoa_solution(candidate_map, qubo, request))
        except Exception as exc:  # pragma: no cover - defensive boundary around optional code
            result_queue.put((None, None, None, None, f"QAOA worker failed: {type(exc).__name__}: {exc}"))

    thread = threading.Thread(target=worker, name="qhexroute-qaoa", daemon=True)
    thread.start()
    thread.join(QAOA_TIMEOUT_SECONDS)
    if thread.is_alive():
        return None, None, None, None, f"QAOA timed out after {QAOA_TIMEOUT_SECONDS:g} seconds; classical fallback was used."
    try:
        return result_queue.get_nowait()
    except queue.Empty:  # pragma: no cover - defensive boundary around optional code
        return None, None, None, None, "QAOA returned no result; classical fallback was used."


def run_id_for(request: OptimizeRequest) -> str:
    stamp = f"{request.seed}:{request.incident.model_dump_json()}:{time.time_ns()}".encode()
    return "run_" + hashlib.sha1(stamp).hexdigest()[:10]


def route_payload(route: Route, selected: bool = False) -> dict[str, Any]:
    return {
        "vehicle_id": route.vehicle_id,
        "route_id": route.route_id,
        "path": list(route.path),
        "edge_ids": list(route.edge_ids),
        "distance_m": route.distance_m,
        "travel_time_s": route.travel_time_s,
        "congestion": route.congestion,
        "incident_risk": route.incident_risk,
        "affected_cells": list(route.affected_cells),
        "geometry": route.geometry,
        "selected": selected,
    }


def feature_lines(routes: list[Route]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"vehicle_id": route.vehicle_id, "route_id": route.route_id}, "geometry": route.geometry} for route in routes]}


engine = ScenarioEngine()
app = FastAPI(title="Q-HexRoute API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4321", "http://127.0.0.1:4321", "http://localhost:4322", "http://127.0.0.1:4322"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    quantum_available = False
    try:
        import qiskit  # noqa: F401
        quantum_available = os.getenv("QHEXROUTE_ENABLE_QAOA", "0") == "1"
    except ImportError:
        pass
    return {"status": "ok", "graph_ready": True, "qiskit_ready": quantum_available, "app_version": APP_VERSION}


def road_network_payload(scenario_engine: ScenarioEngine) -> dict[str, Any]:
    features = []
    for source, target, data in scenario_engine.graph.edges(data=True):
        coordinates = _geometry_coordinates(data.get("geometry_coords"), source, target, scenario_engine.graph)
        features.append({
            "type": "Feature",
            "properties": {"edge_id": data["edge_id"], "source": source, "target": target, "congestion": data["congestion"]},
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })
    return {"type": "FeatureCollection", "features": features}


def routing_bounds(graph: nx.DiGraph) -> list[list[float]]:
    longitudes = [float(data["lon"]) for _, data in graph.nodes(data=True)]
    latitudes = [float(data["lat"]) for _, data in graph.nodes(data=True)]
    padding = 0.002
    return [[min(longitudes) - padding, min(latitudes) - padding], [max(longitudes) + padding, max(latitudes) + padding]]


def scenario_payload(scenario_engine: ScenarioEngine) -> dict[str, Any]:
    routes = [scenario_engine.current_route(vehicle) for vehicle in scenario_engine.vehicles]
    coverage = city_h3_coverage()
    route_coverage = route_h3_coverage(routes, H3_RESOLUTION)
    graph_source = scenario_engine.graph.graph.get("source", "synthetic")
    return {
        "road_network": road_network_payload(scenario_engine),
        "h3_resolution": H3_RESOLUTION,
        "vehicles": [{**vehicle, "current_route": route_payload(route)} for vehicle, route in zip(scenario_engine.vehicles, routes)],
        "bounds": [[LON_MIN, LAT_MIN], [LON_MAX, LAT_MAX]],
        "routing_bounds": routing_bounds(scenario_engine.graph),
        "incident": Incident().model_dump(),
        "seed": scenario_engine.seed,
        "graph_source": graph_source,
        "city": {"name": CITY_NAME, "alias": CITY_ALIAS, "region": CITY_REGION, "coverage_label": "Approximate urban study envelope"},
        "h3_coverage": {"resolution": coverage["resolution"], "cell_count": coverage["cell_count"], "cells_geojson": coverage["cells_geojson"]},
        "route_h3_coverage": route_coverage,
        "attribution": "OpenStreetMap driving graph · Bengaluru urban envelope" if graph_source == "openstreetmap" else "Approximate Bengaluru urban envelope · synthetic fallback graph",
    }


@app.get("/api/scenario")
def scenario(seed: int = Query(DEFAULT_SEED, ge=0, le=999999)) -> dict[str, Any]:
    return scenario_payload(ScenarioEngine(seed))


@app.post("/api/incidents/preview")
def preview(request: PreviewRequest) -> dict[str, Any]:
    localization = ScenarioEngine(request.seed).localization(request, request.h3_resolution, request.seed)
    return {
        "incident": request.model_dump(),
        "affected_region": {"cells_geojson": localization["cells"]["geojson"], "cell_ids": localization["cells"]["ids"], "edge_count": len(localization["affected_edge_ids"]), "vehicle_count": len(localization["affected_vehicle_ids"])},
        "affected_edge_ids": localization["affected_edge_ids"],
        "affected_vehicle_ids": localization["affected_vehicle_ids"],
        "localization": {"total_vehicles": localization["total_vehicles"], "affected_vehicles": len(localization["affected_vehicle_ids"]), "variables_without_localization": localization["total_vehicles"] * 3, "variables_with_localization": len(localization["affected_vehicle_ids"]) * 2},
    }


@app.post("/api/optimize")
def optimize(request: OptimizeRequest) -> dict[str, Any]:
    started = time.perf_counter()
    scenario_engine = ScenarioEngine(request.seed)
    localization_started = time.perf_counter()
    localization = scenario_engine.localization(request.incident, request.h3_resolution, request.seed)
    affected_ids = set(localization["affected_vehicle_ids"])
    localization_ms = (time.perf_counter() - localization_started) * 1000
    candidates_started = time.perf_counter()
    candidate_map: dict[str, list[Route]] = {}
    vehicles_by_id = {vehicle["id"]: vehicle for vehicle in scenario_engine.vehicles}
    cell_set = set(localization["cells"]["ids"])
    for vehicle_id in sorted(affected_ids):
        candidates = scenario_engine.candidate_routes(vehicles_by_id[vehicle_id], request.incident, cell_set, set(localization["affected_edge_ids"]), request.candidate_count, request.h3_resolution)
        if candidates:
            candidate_map[vehicle_id] = candidates
    candidate_ms = (time.perf_counter() - candidates_started) * 1000
    qubo_started = time.perf_counter()
    qubo = build_qubo(candidate_map)
    qubo_ms = (time.perf_counter() - qubo_started) * 1000
    exact_started = time.perf_counter()
    exact_selected, exact_metrics = exact_solution(candidate_map)
    exact_ms = (time.perf_counter() - exact_started) * 1000
    greedy_started = time.perf_counter()
    greedy_selected, greedy_metrics = greedy_solution(candidate_map)
    greedy_ms = (time.perf_counter() - greedy_started) * 1000

    variables = len(qubo["variables"])
    qaoa_requested = request.solver_mode in {"qaoa", "compare"}
    qaoa_attempted = qaoa_requested and os.getenv("QHEXROUTE_ENABLE_QAOA", "0") == "1" and 0 < variables <= QAOA_VARIABLE_CAP
    qaoa_selected: list[Route] = []
    qaoa_metrics = {"total": None, "route_cost": None, "overlap": None}
    qaoa_reason: str | None = None
    qaoa_solver = "classical_fallback"
    qaoa_bitstring: str | None = None
    qaoa_iterations: int | None = None
    quantum_started = time.perf_counter()
    if qaoa_requested:
        if not qaoa_attempted:
            qaoa_reason = ("No candidate decisions to send to QAOA." if variables == 0 else
                           f"QAOA cap exceeded: {variables} variables > {QAOA_VARIABLE_CAP}." if variables > QAOA_VARIABLE_CAP else
                           "Optional Qiskit stack is not enabled in this local prototype.")
            qaoa_selected, qaoa_metrics = exact_selected, exact_metrics
        else:
            quantum_result = qaoa_solution_with_timeout(candidate_map, qubo, request)
            qaoa_selected, qaoa_metrics, qaoa_bitstring, qaoa_iterations, qaoa_reason = quantum_result
            if qaoa_selected is not None and qaoa_metrics is not None:
                qaoa_solver = "qaoa"
            else:
                qaoa_selected, qaoa_metrics = exact_selected, exact_metrics
    quantum_ms = (time.perf_counter() - quantum_started) * 1000

    if not affected_ids:
        # There is no assignment to solve for a no-change incident. Report the
        # exact empty reference rather than labelling this a quantum fallback.
        selected, selected_metrics, solver_used = [], exact_metrics, "exact"
        qaoa_reason = None
    elif request.solver_mode == "classical":
        selected, selected_metrics, solver_used = exact_selected, exact_metrics, "exact"
    elif request.solver_mode == "qaoa":
        selected, selected_metrics, solver_used = qaoa_selected, qaoa_metrics, qaoa_solver
    else:
        selected, selected_metrics, solver_used = qaoa_selected, qaoa_metrics, qaoa_solver

    all_candidate_routes = [route for routes in candidate_map.values() for route in routes]
    affected_current = [localization_route for localization_route in localization["current_routes"] if localization_route.vehicle_id in affected_ids]
    unaffected = [localization_route for localization_route in localization["current_routes"] if localization_route.vehicle_id not in affected_ids]
    selected_ids = {route.vehicle_id: route.route_id for route in selected}
    unroutable_ids = sorted(affected_ids - set(selected_ids))
    feasible = not unroutable_ids and len(selected_ids) == len(selected) and set(selected_ids) == affected_ids
    run_id = run_id_for(request)
    exact_total = exact_metrics["total"]
    final_total = selected_metrics["total"]
    comparison_gap = ((final_total - exact_total) / abs(exact_total) * 100) if exact_total and final_total is not None else 0.0
    qaoa_comparison_total = qaoa_metrics["total"] if qaoa_solver == "qaoa" else None
    response = {
        "run_id": run_id,
        "status": "no_change" if not affected_ids else "success" if feasible else "partial",
        "solver_used": solver_used,
        "fallback_reason": qaoa_reason if solver_used == "classical_fallback" else None,
        "feasible": feasible,
        "unroutable_vehicle_ids": unroutable_ids,
        "repaired": False,
        "incident": request.incident.model_dump(),
        "affected_region": {"cells_geojson": localization["cells"]["geojson"], "cell_ids": localization["cells"]["ids"], "edge_count": len(localization["affected_edge_ids"]), "vehicle_count": len(affected_ids)},
        "localization": {"total_vehicles": len(scenario_engine.vehicles), "affected_vehicles": len(affected_ids), "variables_without_localization": len(scenario_engine.vehicles) * request.candidate_count, "variables_with_localization": variables, "reduction_percent": round((1 - variables / max(len(scenario_engine.vehicles) * request.candidate_count, 1)) * 100, 1)},
        "selected_routes": [route_payload(route, True) for route in selected],
        "candidate_routes": [route_payload(route, route.route_id == selected_ids.get(route.vehicle_id)) for route in all_candidate_routes],
        "unaffected_routes": [route_payload(route) for route in unaffected],
        "current_routes": [route_payload(route) for route in affected_current],
        "road_network": road_network_payload(scenario_engine),
        # The map can show original affected routes and legal alternatives in
        # addition to the final selection. Keep the H3 overlay authoritative
        # for every route that can be visible in any comparison view.
        "route_h3_coverage": route_h3_coverage(
            [*selected, *unaffected, *affected_current, *all_candidate_routes], request.h3_resolution
        ),
        "objective": {"total": round(final_total, 5) if final_total is not None else None, "travel_time": round(sum(route.travel_time_s for route in selected), 2), "distance": round(sum(route.distance_m for route in selected), 1), "congestion": round(sum(route.congestion for route in selected), 4), "incident_risk": round(sum(route.incident_risk for route in selected), 4), "overlap": round(selected_metrics["overlap"], 5) if selected_metrics["overlap"] is not None else None},
        "comparison": {"greedy_objective": round(greedy_metrics["total"], 5), "exact_objective": round(exact_total, 5), "qaoa_objective": round(qaoa_comparison_total, 5) if qaoa_comparison_total is not None else None, "optimality_gap_percent": round(comparison_gap, 2)},
         "quantum": {"attempted": qaoa_attempted, "backend": "local_simulator", "variables": variables, "qubits": variables if qaoa_bitstring is not None else None, "qaoa_depth": request.qaoa_depth, "shots": request.shots, "optimizer_iterations": qaoa_iterations, "optimizer_iteration_limit": QAOA_MAX_ITERATIONS, "timeout_seconds": QAOA_TIMEOUT_SECONDS, "circuit_depth": None, "two_qubit_gate_count": None, "best_bitstring": qaoa_bitstring, "raw_sample_feasible": (solver_used == "qaoa") if qaoa_bitstring is not None else None, "final_solution_feasible": feasible, "repair_or_fallback": solver_used == "classical_fallback", "cap": QAOA_VARIABLE_CAP},
        "timing_ms": {"localization": round(localization_ms, 2), "candidate_generation": round(candidate_ms, 2), "qubo_build": round(qubo_ms, 2), "classical": round(greedy_ms + exact_ms, 2), "qaoa": round(quantum_ms, 2), "total": round((time.perf_counter() - started) * 1000, 2)},
        "metadata": {"seed": request.seed, "weights": WEIGHTS, "qubo": qubo, "candidate_count": request.candidate_count},
    }
    engine.runs[run_id] = response
    return response


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    if run_id not in engine.runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return engine.runs[run_id]
