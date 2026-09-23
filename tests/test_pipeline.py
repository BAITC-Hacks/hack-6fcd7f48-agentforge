import math
from pathlib import Path

import pandas as pd
import pytest

from backend.pipeline import analyze, load_data

ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}


def test_complete_snapshot_including_boundary_and_isolate(sample_data: Path, tmp_path: Path):
    snapshot = analyze(sample_data, tmp_path / "out")
    nodes = {n["gid"]: n for n in snapshot.nodes}
    assert set(nodes) == {"1", "2", "3", "4", "5", "6"}
    assert snapshot.summary["n_isolates"] == 1
    assert snapshot.summary["n_components"] == 2
    assert snapshot.summary["n_boundary"] == 1
    assert nodes["4"]["boundary"] is True
    assert nodes["4"]["role"] != "terminal"
    assert nodes["5"]["in_degree"] == nodes["5"]["out_degree"] == 0
    assert nodes["1"]["pass_through"] is None
    assert nodes["5"]["pass_through"] is None
    assert sum(c["n_nodes"] for c in snapshot.clusters) == len(nodes)
    assert sum(c["n_seed"] for c in snapshot.clusters) == 2
    assert all(n["role"] in ROLES for n in nodes.values())
    assert all(0 <= n["role_score"] <= 1 and 0 <= n["priority_score"] <= 1 for n in nodes.values())
    assert all(n["evidence"] and len(n["evidence"]) <= 200 for n in nodes.values())
    assert all(math.isfinite(n["pagerank"]) for n in nodes.values())
    assert [n["priority_score"] for n in snapshot.top] == sorted(
        [n["priority_score"] for n in snapshot.top], reverse=True
    )
    filenames = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}
    assert set(snapshot.exports) == filenames
    assert set((tmp_path / "out").iterdir()) == {tmp_path / "out" / name for name in filenames}
    assert all(
        (tmp_path / "out" / name).read_bytes() == snapshot.exports[name] for name in filenames
    )


def test_export_bytes_independent_of_input_order(sample_data: Path, tmp_path: Path):
    names = ("nodes.parquet", "edges.parquet", "transactions.parquet")
    first = analyze(sample_data, tmp_path / "first")
    shuffled_data = tmp_path / "shuffled"
    shuffled_data.mkdir()
    for name in names:
        pd.read_parquet(sample_data / name).sample(frac=1, random_state=26).to_parquet(
            shuffled_data / name, index=False
        )
    second = analyze(shuffled_data, tmp_path / "second")
    for filename in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        assert first.exports[filename] == second.exports[filename]
    repeat = analyze(sample_data, tmp_path / "repeat")
    for filename in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        assert first.exports[filename] == repeat.exports[filename]


def test_public_exports_are_plain_files_and_prior_snapshot_bytes_stay_readable(
    sample_data: Path, tmp_path: Path
):
    out = tmp_path / "out"
    original = analyze(sample_data, out)
    original_bytes = original.exports.copy()
    assert not (out / "current").exists()
    assert all((out / name).is_file() and not (out / name).is_symlink() for name in original_bytes)
    edges_path = sample_data / "edges.parquet"
    tx_path = sample_data / "transactions.parquet"
    edges = pd.read_parquet(edges_path)
    tx = pd.read_parquet(tx_path)
    edges.loc[0, "sum_kzt"] += 100
    tx.loc[0, "sum_kzt"] += 100
    edges.to_parquet(edges_path, index=False)
    tx.to_parquet(tx_path, index=False)
    updated = analyze(sample_data, out)
    for name, before in original_bytes.items():
        assert original.exports[name] == before
        assert (out / name).read_bytes() == updated.exports[name]
    assert original.exports["nodes_roles.csv"] != updated.exports["nodes_roles.csv"]
    assert not (out / "current").exists()


def test_analysis_without_write_returns_exports_without_creating_out(
    sample_data: Path, tmp_path: Path
):
    out = tmp_path / "out"
    snapshot = analyze(sample_data, out, write=False)
    assert not out.exists()
    assert set(snapshot.exports) == {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}
    assert all(snapshot.exports.values())


@pytest.mark.parametrize(
    ("filename", "column", "value", "message"),
    [
        ("nodes.parquet", "gid", 2, "дубликаты"),
        ("nodes.parquet", "is_seed", None, "null"),
        ("edges.parquet", "src", 999, "gid"),
        ("edges.parquet", "sum_kzt", float("inf"), "sum_kzt"),
        ("transactions.parquet", "date", "not-a-date", "date"),
        ("transactions.parquet", "sum_kzt", 11, "суммы"),
    ],
)
def test_rejects_corrupt_inputs(sample_data: Path, filename: str, column: str, value, message: str):
    path = sample_data / filename
    frame = pd.read_parquet(path)
    if value is None or value == float("inf"):
        frame[column] = frame[column].astype(object)
    frame.loc[0, column] = value
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match=message):
        load_data(sample_data)


def test_rejects_missing_column_and_file(sample_data: Path):
    path = sample_data / "edges.parquet"
    frame = pd.read_parquet(path).drop(columns=["n_tx"])
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="n_tx"):
        load_data(sample_data)
    path.unlink()
    with pytest.raises(ValueError, match="Нет файла"):
        load_data(sample_data)


@pytest.mark.parametrize(
    ("filename", "column", "kind", "expected"),
    [
        ("nodes.parquet", "gid", "numeric_string", "nodes.gid"),
        ("nodes.parquet", "gid", "fractional", "nodes.gid"),
        ("nodes.parquet", "gid", "infinite", "nodes.gid"),
        ("nodes.parquet", "gid", "out_of_int64", "nodes.gid"),
        ("nodes.parquet", "gid", "boolean", "nodes.gid"),
        ("edges.parquet", "sum_kzt", "numeric_string", "edges.sum_kzt"),
        ("transactions.parquet", "sum_kzt", "numeric_string", "transactions.sum_kzt"),
        ("transactions.parquet", "date", "numeric_date", "transactions.date"),
    ],
)
def test_strict_parquet_field_types(
    sample_data: Path, filename: str, column: str, kind: str, expected: str
):
    path = sample_data / filename
    frame = pd.read_parquet(path)
    if kind == "numeric_string":
        frame[column] = frame[column].astype(str)
    elif kind == "fractional":
        frame[column] = frame[column].astype(float)
        frame.loc[0, column] += 0.5
    elif kind == "infinite":
        frame[column] = frame[column].astype(float)
        frame.loc[0, column] = float("inf")
    elif kind == "out_of_int64":
        frame[column] = frame[column].astype("uint64")
        frame.loc[0, column] = 2**63
    elif kind == "boolean":
        frame[column] = True
    elif kind == "numeric_date":
        frame[column] = 20260701
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match=expected):
        load_data(sample_data)


def test_finite_rows_cannot_overflow_node_or_summary_totals(tmp_path: Path):
    data = tmp_path / "large-money"
    data.mkdir()
    pd.DataFrame(
        [(1, 0, True), (2, 0, True), (3, 1, False)],
        columns=["gid", "depth", "is_seed"],
    ).to_parquet(data / "nodes.parquet", index=False)
    pd.DataFrame(
        [(1, 3, 1e308, 1, 1), (2, 3, 1e308, 1, 1)],
        columns=["src", "dst", "sum_kzt", "n_tx", "depth"],
    ).to_parquet(data / "edges.parquet", index=False)
    pd.DataFrame(
        [(1, 3, "2026-07-01", 1e308), (2, 3, "2026-07-01", 1e308)],
        columns=["src", "dst", "date", "sum_kzt"],
    ).to_parquet(data / "transactions.parquet", index=False)
    with pytest.raises(ValueError, match="sum_kzt|сумм|переполн|конечн"):
        analyze(data, tmp_path / "out", write=False)
