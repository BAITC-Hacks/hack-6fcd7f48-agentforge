import math

import networkx as nx
import pandas as pd
import pytest

from backend import pipeline


def test_seed_paths_deduplicate_seeds_and_ignore_cycles_and_sideways_edges():
    nodes = pd.DataFrame(
        [
            (1, 0, True),
            (2, 0, True),
            (10, 1, False),
            (11, 1, False),
            (12, 1, False),
            (20, 2, False),
            (30, 3, False),
        ],
        columns=["gid", "depth", "is_seed"],
    )
    edges = [
        (1, 11),
        (1, 10),
        (2, 12),
        (10, 20),
        (11, 20),
        (12, 20),
        (20, 30),
        (30, 10),
        (10, 11),
        (20, 1),
    ]
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.gid)
    graph.add_edges_from(edges)
    paths = pipeline._seed_paths(graph, nodes)
    assert paths[1] == {1: ["1"]}
    assert paths[2] == {2: ["2"]}
    assert paths[20] == {1: ["1", "10", "20"], 2: ["2", "12", "20"]}
    assert paths[30] == {1: ["1", "10", "20", "30"], 2: ["2", "12", "20", "30"]}
    reversed_graph = nx.DiGraph()
    reversed_graph.add_nodes_from(reversed(list(nodes.gid)))
    reversed_graph.add_edges_from(reversed(edges))
    assert pipeline._seed_paths(reversed_graph, nodes.sample(frac=1, random_state=7)) == paths


def _record_graph():
    nodes = pd.DataFrame(
        [
            (1, 0, True),
            (2, 0, True),
            (3, 0, True),
            (4, 0, True),
            (10, 1, False),
            (11, 1, False),
            (20, 2, False),
            (30, 3, False),
            (31, 3, False),
        ],
        columns=["gid", "depth", "is_seed"],
    )
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.gid)
    for src, dst, amount in [
        (1, 10, 10000),
        (2, 10, 10000),
        (3, 10, 10000),
        (1, 11, 10000),
        (2, 11, 10000),
        (3, 11, 10000),
        (10, 20, 10000),
        (11, 20, 10000),
        (20, 30, 5000),
        (20, 31, 5000),
    ]:
        graph.add_edge(src, dst, weight=amount, n_tx=1)
    communities = [{1, 2, 3, 4, 10, 11, 20}, {30}, {31}]
    components = [{1, 2, 3, 10, 11, 20, 30, 31}, {4}]
    return graph, nodes, communities, components


def test_role_order_branch_convergence_and_priority_arithmetic():
    records, _ = pipeline._prioritize(pipeline._node_records(*_record_graph()))
    by_gid = {int(record["gid"]): record for record in records}
    assert by_gid[10]["role"] == by_gid[11]["role"] == "consolidator"
    assert by_gid[20]["role"] == "coordinator"
    assert by_gid[20]["seed_source_count"] == 3
    assert by_gid[20]["collecting_branches"] == 2
    assert by_gid[20]["outgoing_communities"] == 2
    assert by_gid[20]["seed_paths"][:3] == [["1", "10", "20"], ["2", "10", "20"], ["3", "10", "20"]]
    assert by_gid[4]["role"] == "peripheral"
    assert by_gid[4]["seed_source_count"] == 0
    assert by_gid[4]["priority_score"] == 0
    assert by_gid[1]["priority_factor"] == 0.5
    assert by_gid[30]["role"] == "terminal"

    coordinator = by_gid[20]
    expected = 0.35 * (3 / 4) + 0.30 * (2 / 5) + 0.20 * (20000 / 520000) + 0.15 * 0.5 * 0.5
    assert coordinator["priority_score"] == pytest.approx(expected, abs=1e-6)
    for record in records:
        components = record["priority_breakdown"]
        assert len(components) == 4
        assert all(
            {"label", "value", "normalized", "weight"} <= component.keys()
            for component in components
        )
        assert all(
            math.isfinite(component["normalized"]) and 0 <= component["normalized"] <= 1
            for component in components
        )
        assert not any("роль" in component["label"].lower() for component in components)
        contribution = sum(
            component["normalized"] * component["weight"] for component in components
        )
        assert record["priority_score"] == pytest.approx(
            contribution * record["priority_factor"], abs=1e-6
        )
        assert record["priority_reason"]


def test_priority_is_independent_of_role_and_pagerank():
    records = pipeline._node_records(*_record_graph())
    altered = [record.copy() for record in records]
    for record in altered:
        record["role"] = "coordinator"
        record["pagerank"] = 1.0

    original, _ = pipeline._prioritize(records)
    changed, _ = pipeline._prioritize(altered)
    original_scores = {record["gid"]: record["priority_score"] for record in original}
    changed_scores = {record["gid"]: record["priority_score"] for record in changed}
    assert changed_scores == original_scores


def test_seed_and_boundary_never_become_false_terminal_or_coordinator():
    graph = nx.DiGraph()
    graph.add_nodes_from([1, 2, 3, 4, 5, 6, 7, 8])
    for src, dst in [(2, 1), (3, 1), (4, 1), (1, 5), (1, 6), (1, 7), (1, 8)]:
        graph.add_edge(src, dst, weight=5000, n_tx=1)
    nodes = pd.DataFrame(
        [
            (1, 0, True),
            (2, 0, True),
            (3, 0, True),
            (4, 0, True),
            (5, 4, False),
            (6, 4, False),
            (7, 4, False),
            (8, 4, False),
        ],
        columns=["gid", "depth", "is_seed"],
    )
    records, _ = pipeline._prioritize(
        pipeline._node_records(graph, nodes, [set(graph)], [set(graph)])
    )
    by_gid = {int(record["gid"]): record for record in records}
    assert by_gid[1]["role"] != "coordinator"
    assert by_gid[1]["pass_through"] is None
    assert by_gid[1]["seed_source_count"] == 0
    assert by_gid[1]["priority_factor"] == 0.5
    for gid in (5, 6, 7, 8):
        assert by_gid[gid]["role"] != "terminal"
        assert by_gid[gid]["priority_factor"] == 0.85
        assert "Граница" in by_gid[gid]["evidence"]


def test_retention_rule_accepts_two_payers_without_fan_in_and_excludes_seed_boundary():
    nodes = pd.DataFrame(
        [
            (1, 0, True),
            (2, 0, True),
            (3, 0, True),
            (10, 1, False),
            (11, 1, False),
            (12, 4, False),
            (20, 2, False),
            (21, 2, False),
            (22, 2, False),
            (23, 2, False),
            (24, 4, False),
        ],
        columns=["gid", "depth", "is_seed"],
    )
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.gid)
    for src, dst, amount in [
        (2, 1, 100000),
        (3, 1, 100000),
        (1, 10, 50000),
        (2, 10, 50000),
        (2, 11, 10000),
        (3, 11, 10000),
        (1, 12, 50000),
        (2, 12, 50000),
        (10, 20, 5000),
        (10, 21, 5000),
        (10, 22, 5000),
        (11, 23, 30000),
        (12, 24, 5000),
    ]:
        graph.add_edge(src, dst, weight=amount, n_tx=1)
    records = pipeline._node_records(graph, nodes, [set(graph)], [set(graph)])
    by_gid = {int(record["gid"]): record for record in records}

    assert (by_gid[10]["in_degree"], by_gid[10]["out_degree"]) == (2, 3)
    assert by_gid[10]["pass_through"] == pytest.approx(0.15)
    assert by_gid[10]["role"] == "consolidator"
    assert by_gid[11]["pass_through"] == pytest.approx(1.5)
    assert by_gid[11]["role"] != "consolidator"
    assert by_gid[12]["pass_through"] == pytest.approx(0.05)
    assert by_gid[12]["role"] != "consolidator"
    assert by_gid[1]["in_degree"] == 2
    assert by_gid[1]["pass_through"] is None
    assert by_gid[1]["role"] != "consolidator"


def test_coordinator_counts_retaining_predecessors_at_greater_depth():
    nodes = pd.DataFrame(
        [
            (1, 0, True),
            (2, 0, True),
            (10, 3, False),
            (11, 3, False),
            (20, 2, False),
            (30, 3, False),
            (31, 3, False),
        ],
        columns=["gid", "depth", "is_seed"],
    )
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.gid)
    for src, dst, amount in [
        (1, 10, 50000),
        (2, 10, 50000),
        (1, 11, 50000),
        (2, 11, 50000),
        (10, 20, 10000),
        (11, 20, 10000),
        (20, 30, 5000),
        (20, 31, 5000),
    ]:
        graph.add_edge(src, dst, weight=amount, n_tx=1)
    records = pipeline._node_records(graph, nodes, [set(graph)], [set(graph)])
    by_gid = {int(record["gid"]): record for record in records}

    assert by_gid[10]["role"] == by_gid[11]["role"] == "consolidator"
    assert by_gid[20]["seed_source_count"] == 0
    assert by_gid[20]["collecting_branches"] == 2
    assert by_gid[20]["pass_through"] == pytest.approx(0.5)
    assert by_gid[20]["role"] == "coordinator"
