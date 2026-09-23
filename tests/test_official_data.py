import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from backend.pipeline import analyze

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.mark.skipif(
    not all(
        (DATA / name).is_file()
        for name in ("nodes.parquet", "edges.parquet", "transactions.parquet")
    ),
    reason="Official parquet files are not present in this checkout",
)
def test_official_cli_under_five_minutes_and_semantic_spot_checks(tmp_path: Path):
    output = tmp_path / "exports"
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "backend.pipeline", "--data", str(DATA), "--out", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    elapsed = time.perf_counter() - started
    assert result.returncode == 0, result.stderr
    assert elapsed < 300
    with (output / "nodes_roles.csv").open(newline="", encoding="utf-8") as handle:
        roles = list(csv.DictReader(handle))
    with (output / "clusters.csv").open(newline="", encoding="utf-8") as handle:
        clusters = list(csv.DictReader(handle))
    with (output / "top_nodes.csv").open(newline="", encoding="utf-8") as handle:
        top = list(csv.DictReader(handle))
    source_nodes = pd.read_parquet(DATA / "nodes.parquet")
    source_edges = pd.read_parquet(DATA / "edges.parquet")
    source_tx = pd.read_parquet(DATA / "transactions.parquet")
    assert (len(roles), len(source_edges), len(source_tx), int(source_nodes.is_seed.sum())) == (
        2248,
        3119,
        4840,
        81,
    )
    assert {int(row["gid"]) for row in roles} == set(source_nodes.gid)
    assert sum(int(row["n_nodes"]) for row in clusters) == len(roles)
    assert len(top) >= 20
    assert [int(row["rank"]) for row in top] == list(range(1, len(top) + 1))
    by_gid = {int(row["gid"]): row for row in roles}
    ordered_gids = sorted(int(gid) for gid in source_nodes.gid)
    for gid in (ordered_gids[0], ordered_gids[len(ordered_gids) // 2], ordered_gids[-1]):
        row = by_gid[gid]
        assert row["role"] and row["evidence"]
        assert 0 <= float(row["role_score"]) <= 1
        assert 0 <= float(row["priority_score"]) <= 1
        assert any(int(c["cluster_id"]) == int(row["cluster_id"]) for c in clusters)
    valid_roles = {
        "consolidator",
        "transit",
        "distributor",
        "terminal",
        "coordinator",
        "peripheral",
    }
    assert all(row["role"] in valid_roles and 0 < len(row["evidence"]) <= 200 for row in roles)
    assert all(
        math.isfinite(float(row["role_score"]))
        and math.isfinite(float(row["priority_score"]))
        and 0 <= float(row["role_score"]) <= 1
        and 0 <= float(row["priority_score"]) <= 1
        for row in roles
    )
    boundary_gids = set(source_nodes.loc[source_nodes.depth == 4, "gid"])
    assert all(by_gid[gid]["role"] != "terminal" for gid in boundary_gids)
    assert all(float(by_gid[gid]["role_score"]) <= 0.75 for gid in boundary_gids)
    seed_gids = set(source_nodes.loc[source_nodes.is_seed, "gid"])
    assert all(float(by_gid[gid]["role_score"]) <= 0.85 for gid in seed_gids)
    cluster_of = {gid: int(row["cluster_id"]) for gid, row in by_gid.items()}
    expected_internal = {int(row["cluster_id"]): 0 for row in clusters}
    for edge in source_edges.itertuples(index=False):
        if cluster_of[edge.src] == cluster_of[edge.dst]:
            expected_internal[cluster_of[edge.src]] += edge.sum_kzt
    for cluster in clusters:
        cluster_id = int(cluster["cluster_id"])
        members = [gid for gid, assigned in cluster_of.items() if assigned == cluster_id]
        assert len(members) == int(cluster["n_nodes"])
        assert len(seed_gids.intersection(members)) == int(cluster["n_seed"])
        assert float(cluster["sum_kzt_internal"]) == pytest.approx(
            expected_internal[cluster_id], abs=0.01
        )
        assert set(map(int, filter(None, cluster["top_gids"].split(",")))) <= set(members)
    expected_top = sorted(roles, key=lambda row: (-float(row["priority_score"]), int(row["gid"])))
    assert [row["gid"] for row in top] == [row["gid"] for row in expected_top[: len(top)]]
    assert all(row["why"] and row["role"] == by_gid[int(row["gid"])]["role"] for row in top)

    shuffled = tmp_path / "shuffled"
    shuffled.mkdir()
    for filename in ("nodes.parquet", "edges.parquet", "transactions.parquet"):
        pd.read_parquet(DATA / filename).sample(frac=1, random_state=73).to_parquet(
            shuffled / filename, index=False
        )
    shuffled_snapshot = analyze(shuffled, tmp_path / "shuffled-exports")
    json.dumps(
        {
            "nodes": shuffled_snapshot.nodes,
            "edges": shuffled_snapshot.edges,
            "clusters": shuffled_snapshot.clusters,
            "top": shuffled_snapshot.top,
            "summary": shuffled_snapshot.summary,
        },
        allow_nan=False,
    )
    for filename in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        assert (output / filename).read_bytes() == (
            shuffled_snapshot.output_dir / filename
        ).read_bytes()
