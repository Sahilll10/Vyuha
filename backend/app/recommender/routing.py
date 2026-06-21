"""
Diversion routing — roadmap section 7.3.

Primary path: pull Bengaluru's real OpenStreetMap drive-network graph with
OSMnx (free, no API key — exactly the kind of mapping integration the
hackathon's MapmyIndia partnership signals judges will recognize as
"on-brand"), cache it to disk, and use NetworkX's k-shortest-simple-paths
to compute 2-3 alternate routes around a blocked node.

Fallback path: OSMnx needs outbound internet access to the Overpass API,
which isn't guaranteed during a live demo (conference wifi, judging-room
firewalls, free-tier hosting egress rules). Rather than let the what-if
demo crash the moment the network blips, we build a small graph directly
from the dataset's own ~294 junction coordinates (k-nearest-neighbor,
haversine-weighted) and route over that instead. The response always
reports which mode served the request (`routing_mode`) — never silently
pretends a fallback is the real road network.

Both graph variants are kept as plain (non-multi) `networkx.Graph` /
`networkx.DiGraph` objects with `length` (meters) and `travel_time`
(seconds) edge attributes and `y`/`x` node attributes, so every query
method below works identically regardless of which mode is active.
"""
from __future__ import annotations

import itertools
import logging
import os
from typing import Optional

import networkx as nx
import pandas as pd

from app.config import settings
from app.utils import geo_utils

logger = logging.getLogger("vyuha.routing")

try:
    import osmnx as ox
    _OSMNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OSMNX_AVAILABLE = False

_DEFAULT_FALLBACK_SPEED_KMH = 30.0


def _simplify_to_simple_graph(G):
    """
    nx.shortest_simple_paths requires a graph without parallel edges.
    OSMnx graphs are MultiDiGraphs; collapse each (u, v) multi-edge down to
    its shortest variant. No-op for graphs that are already simple.
    """
    if not isinstance(G, (nx.MultiDiGraph, nx.MultiGraph)):
        return G
    H = nx.DiGraph() if G.is_directed() else nx.Graph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v, data in G.edges(data=True):
        length = data.get("length", 1.0)
        if H.has_edge(u, v):
            if length < H[u][v].get("length", float("inf")):
                H[u][v].update(data)
        else:
            H.add_edge(u, v, **data)
    return H


def _edge_attr(G, u, v, key, default=0.0):
    data = G.get_edge_data(u, v) or {}
    return data.get(key, default)


class RoadGraphProvider:
    def __init__(self):
        self.graph = None
        self.mode: Optional[str] = None  # "osm" | "fallback"

    @property
    def using_fallback(self) -> bool:
        return self.mode == "fallback"

    @property
    def is_ready(self) -> bool:
        return self.graph is not None and self.graph.number_of_nodes() > 0

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, junctions_df: Optional[pd.DataFrame] = None) -> "RoadGraphProvider":
        cache_path = settings.OSM_GRAPH_CACHE

        if _OSMNX_AVAILABLE and os.path.exists(cache_path):
            try:
                G = ox.load_graphml(cache_path)
                self.graph = _simplify_to_simple_graph(G)
                self.mode = "osm"
                logger.info("RoadGraphProvider: loaded cached OSM graph from %s", cache_path)
                return self
            except Exception as e:
                logger.warning("RoadGraphProvider: failed to load cached graph (%s)", e)

        if _OSMNX_AVAILABLE:
            try:
                G = ox.graph_from_place(settings.OSM_PLACE_NAME, network_type="drive")
                G = ox.add_edge_speeds(G)
                G = ox.add_edge_travel_times(G)
                ox.save_graphml(G, cache_path)
                self.graph = _simplify_to_simple_graph(G)
                self.mode = "osm"
                logger.info("RoadGraphProvider: downloaded live OSM graph for %s", settings.OSM_PLACE_NAME)
                return self
            except Exception as e:
                logger.warning(
                    "RoadGraphProvider: OSM download unavailable (%s) — using dataset-derived fallback graph.", e
                )

        self.graph = self._build_fallback_graph(junctions_df)
        self.mode = "fallback"
        logger.info(
            "RoadGraphProvider: fallback graph ready (%d nodes, %d edges).",
            self.graph.number_of_nodes(), self.graph.number_of_edges(),
        )
        return self

    @staticmethod
    def _build_fallback_graph(junctions_df: Optional[pd.DataFrame], k: int = 4) -> nx.Graph:
        """
        k-nearest-neighbor graph over the dataset's own junction coordinates.
        Not a real road network — every edge is "as the crow flies" — but it
        is real Bengaluru geography, requires zero internet access, and keeps
        the what-if demo's diversion feature functional offline.

        junctions_df expects columns: node_id, lat, lon.
        """
        G = nx.Graph()
        if junctions_df is None or len(junctions_df) == 0:
            return G

        records = junctions_df.to_dict("records")
        for r in records:
            G.add_node(r["node_id"], y=float(r["lat"]), x=float(r["lon"]))

        n = len(records)
        for i in range(n):
            lat_i, lon_i = records[i]["lat"], records[i]["lon"]
            dists = []
            for j in range(n):
                if i == j:
                    continue
                d_km = geo_utils.haversine_km(lat_i, lon_i, records[j]["lat"], records[j]["lon"])
                dists.append((d_km, j))
            dists.sort(key=lambda t: t[0])
            for d_km, j in dists[:k]:
                u, v = records[i]["node_id"], records[j]["node_id"]
                length_m = max(d_km * 1000.0, 1.0)
                travel_time_s = length_m / 1000.0 / _DEFAULT_FALLBACK_SPEED_KMH * 3600.0
                if G.has_edge(u, v):
                    if length_m < G[u][v]["length"]:
                        G[u][v].update(length=length_m, travel_time=travel_time_s)
                else:
                    G.add_edge(u, v, length=length_m, travel_time=travel_time_s)
        return G

    # ── Query ────────────────────────────────────────────────────────────────

    def nearest_node(self, lat: float, lon: float):
        if self.graph is None or self.graph.number_of_nodes() == 0:
            return None
        if self.mode == "osm" and _OSMNX_AVAILABLE:
            try:
                return ox.distance.nearest_nodes(self.graph, lon, lat)
            except Exception:
                pass
        best_node, best_dist = None, float("inf")
        for node, data in self.graph.nodes(data=True):
            d = geo_utils.haversine_km(lat, lon, data.get("y", 0.0), data.get("x", 0.0))
            if d < best_dist:
                best_dist, best_node = d, node
        return best_node

    def suggest_diversions(self, lat: float, lon: float, max_routes: int = 3) -> dict:
        """
        Treats the node nearest to (lat, lon) as blocked, and finds up to
        `max_routes` alternate paths between its two best-connected
        neighbors that avoid it entirely.
        """
        if self.graph is None or self.graph.number_of_nodes() < 3:
            return {
                "routes": [], "baseline_distance_km": None,
                "routing_mode": self.mode or "fallback",
                "note": "Road graph is not loaded.",
            }

        blocked = self.nearest_node(lat, lon)
        if blocked is None:
            return {
                "routes": [], "baseline_distance_km": None, "routing_mode": self.mode,
                "note": "Could not locate a graph node near the incident.",
            }

        if self.graph.is_directed():
            neighbors = sorted(set(list(self.graph.successors(blocked)) + list(self.graph.predecessors(blocked))))
        else:
            neighbors = sorted(self.graph.neighbors(blocked))

        if len(neighbors) < 2:
            return {
                "routes": [], "baseline_distance_km": None, "routing_mode": self.mode,
                "note": "Incident location has too few connecting roads for diversion routing.",
            }

        origin, destination = neighbors[0], neighbors[-1]

        baseline_km = None
        try:
            baseline_m = nx.shortest_path_length(self.graph, origin, destination, weight="length")
            baseline_km = round(baseline_m / 1000.0, 3)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        H = self.graph.copy()
        H.remove_node(blocked)

        routes = []
        try:
            paths_gen = nx.shortest_simple_paths(H, origin, destination, weight="length")
            for rank, path in enumerate(itertools.islice(paths_gen, max_routes), start=1):
                coords = [[self.graph.nodes[n]["y"], self.graph.nodes[n]["x"]] for n in path]
                dist_m = sum(_edge_attr(H, u, v, "length", 0.0) for u, v in zip(path[:-1], path[1:]))
                dist_km = round(dist_m / 1000.0, 3)
                time_s = sum(
                    _edge_attr(H, u, v, "travel_time", _edge_attr(H, u, v, "length", 0.0) / 1000.0 / _DEFAULT_FALLBACK_SPEED_KMH * 3600.0)
                    for u, v in zip(path[:-1], path[1:])
                )
                extra_km = round(max(0.0, dist_km - (baseline_km or dist_km)), 3)
                routes.append({
                    "rank": rank,
                    "coordinates": coords,
                    "distance_km": dist_km,
                    "extra_distance_km": extra_km,
                    "estimated_minutes": round(time_s / 60.0, 1),
                    "description": (
                        f"Alternate route #{rank} avoiding the incident point "
                        f"({dist_km} km, ~{round(time_s / 60.0, 1)} min)."
                    ),
                })
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        note = None
        if self.mode == "fallback":
            note = (
                "Approximate routing: live OSM road-network access wasn't available, so this uses a "
                "graph built from the dataset's own junction coordinates rather than true road geometry."
            )

        return {
            "routes": routes,
            "baseline_distance_km": baseline_km,
            "routing_mode": self.mode or "fallback",
            "note": note,
        }


# Module-level singleton, populated at FastAPI startup (see app/main.py)
road_graph = RoadGraphProvider()
