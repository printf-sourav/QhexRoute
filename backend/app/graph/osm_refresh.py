"""Refresh a local directed driving graph from OpenStreetMap with OSMnx.

The application loads the checked-in GraphML fixture when it is available and
falls back to the deterministic graph only when the fixture is absent. Refresh
is an explicit developer action so normal app startup does not call Nominatim
or Overpass.
"""

from __future__ import annotations

from pathlib import Path


def refresh_fixture(place: str, output: str, dist: int = 1500) -> Path:
    try:
        import osmnx as ox
    except ImportError as exc:  # pragma: no cover - optional developer tool
        raise RuntimeError("Install backend/requirements-osm.txt to use the OSM refresh helper.") from exc

    latitude, longitude = ox.geocode(place)
    graph = ox.graph_from_point(
        (latitude, longitude),
        dist=dist,
        dist_type="bbox",
        network_type="drive",
        simplify=True,
        retain_all=False,
        truncate_by_edge=True,
    )
    graph.graph["source"] = "openstreetmap"
    graph.graph["source_place"] = place
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, destination)
    return destination
