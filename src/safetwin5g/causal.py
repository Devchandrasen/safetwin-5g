"""Causal-graph validation and fail-closed identification checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_ASSUMPTION_STATUS = {"met", "provisional", "not-met"}
ALLOWED_ESTIMAND_STATUS = {"identified", "provisional", "descriptive-only", "not-identified"}


def load_graph(path: Path) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    validate_graph(graph)
    return graph


def validate_graph(graph: dict[str, Any]) -> None:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("causal graph requires nodes")
    if not isinstance(edges, list):
        raise ValueError("causal graph requires edges")
    node_ids = [str(node.get("id", "")).strip() for node in nodes]
    if any(not node_id for node_id in node_ids) or len(node_ids) != len(set(node_ids)):
        raise ValueError("causal node ids must be non-empty and unique")
    adjacency = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("each causal edge must contain source and target")
        source, target = edge
        if source not in adjacency or target not in adjacency:
            raise ValueError(f"edge references unknown node: {edge}")
        adjacency[source].append(target)
        indegree[target] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    visited = []
    while queue:
        node = queue.pop(0)
        visited.append(node)
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    if len(visited) != len(node_ids):
        raise ValueError("causal graph must be acyclic")
    assumptions = graph.get("assumptions", [])
    if not assumptions:
        raise ValueError("causal graph requires assumptions")
    for assumption in assumptions:
        if assumption.get("status") not in ALLOWED_ASSUMPTION_STATUS:
            raise ValueError(f"invalid assumption status: {assumption}")
    estimands = graph.get("estimands", [])
    if not estimands:
        raise ValueError("causal graph requires estimands")
    for estimand in estimands:
        if estimand.get("status") not in ALLOWED_ESTIMAND_STATUS:
            raise ValueError(f"invalid estimand status: {estimand}")


def identification_report(graph: dict[str, Any]) -> dict[str, Any]:
    validate_graph(graph)
    assumptions = {item["id"]: item["status"] for item in graph["assumptions"]}
    blockers = [
        name
        for name in ("conditional_exchangeability", "positivity", "no_carryover")
        if assumptions.get(name) != "met"
    ]
    return {
        "graph_id": graph["graph_id"],
        "alternative_action_effect_identified": not blockers,
        "blocking_assumptions": blockers,
        "permitted_current_claim": "descriptive paired contrast",
    }
