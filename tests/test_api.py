import asyncio
import csv
import io
import json
from pathlib import Path

import httpx
import pandas as pd

from backend import app as api
from backend.pipeline import analyze


def test_graph_selection_and_export_allowlist(sample_data: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "DATA_DIR", sample_data)
    monkeypatch.setattr(api, "OUT_DIR", tmp_path / "out")

    async def check():
        async with (
            api.app.router.lifespan_context(api.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app), base_url="http://test"
            ) as client,
        ):
            assert (await client.get("/api/health")).json()["ready"] is True
            assert not (tmp_path / "out").exists()
            graph = (await client.get("/api/graph", params={"gid": "2", "limit": 2})).json()
            assert graph["truncated"] is True
            assert graph["total_nodes"] == 4
            assert graph["total_edges"] == 3
            assert graph["nodes"][0]["gid"] == "2"
            selected = {n["gid"] for n in graph["nodes"]}
            assert all(e["src"] in selected and e["dst"] in selected for e in graph["edges"])
            assert (await client.get("/api/graph", params={"gid": "999"})).status_code == 404
            assert (await client.get("/api/nodes/999")).status_code == 404
            page = (await client.get("/api/nodes", params={"limit": 2, "offset": 1})).json()
            assert page["total"] == 6 and len(page["items"]) == 2
            assert page["items"] == api.app.state.snapshot.nodes[1:3]
            assert (await client.get("/api/nodes", params={"limit": 501})).status_code == 422
            for filename, payload in api.app.state.snapshot.exports.items():
                response = await client.get(f"/api/exports/{filename}")
                assert response.status_code == 200
                assert response.content == payload
            assert (await client.get("/api/exports/other.csv")).status_code == 404
            assert (await client.get("/api/exports/..%2Fnodes.parquet")).status_code != 200
            detail = (await client.get("/api/nodes/4")).json()
            assert detail["node"]["boundary"] is True
            assert detail["warnings"]
            seed = (await client.get("/api/nodes/1")).json()
            assert seed["node"]["pass_through"] is None
            assert seed["warnings"]

    asyncio.run(check())


def test_missing_data_keeps_health_available(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "missing")
    monkeypatch.setattr(api, "OUT_DIR", tmp_path / "out")

    async def check():
        async with (
            api.app.router.lifespan_context(api.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app), base_url="http://test"
            ) as client,
        ):
            health = await client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["ready"] is False
            assert "parquet" in health.json()["detail"]
            assert (await client.get("/api/summary")).status_code == 503

    asyncio.run(check())


def test_nonseed_outgoing_exceeds_observed_incoming_is_flagged(
    sample_data: Path, tmp_path: Path, monkeypatch
):
    edges_path = sample_data / "edges.parquet"
    tx_path = sample_data / "transactions.parquet"
    edges = pd.read_parquet(edges_path)
    tx = pd.read_parquet(tx_path)
    edges.loc[edges["dst"] == 6, "sum_kzt"] = 5000
    tx.loc[tx["dst"] == 6, "sum_kzt"] = 5000
    edges.to_parquet(edges_path, index=False)
    tx.to_parquet(tx_path, index=False)
    monkeypatch.setattr(api, "DATA_DIR", sample_data)
    monkeypatch.setattr(api, "OUT_DIR", tmp_path / "out")

    async def check():
        async with (
            api.app.router.lifespan_context(api.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app), base_url="http://test"
            ) as client,
        ):
            detail = (await client.get("/api/nodes/2")).json()
            assert detail["node"]["pass_through"] == 1.4
            assert detail["node"]["role"] != "consolidator"
            assert detail["warnings"]
            assert any("отправлено больше" in warning.lower() for warning in detail["warnings"])
            assert "вход" in detail["node"]["evidence"].lower()

    asyncio.run(check())


def test_signed_int64_ids_survive_csv_and_json(sample_data: Path, tmp_path: Path, monkeypatch):
    ids = {1: -(2**63) + 1, 2: 2**53 + 1}
    for filename, columns in (
        ("nodes.parquet", ("gid",)),
        ("edges.parquet", ("src", "dst")),
        ("transactions.parquet", ("src", "dst")),
    ):
        path = sample_data / filename
        frame = pd.read_parquet(path)
        for column in columns:
            frame[column] = frame[column].replace(ids).astype("int64")
        frame.to_parquet(path, index=False)
    monkeypatch.setattr(api, "DATA_DIR", sample_data)
    monkeypatch.setattr(api, "OUT_DIR", tmp_path / "out")

    async def check():
        async with (
            api.app.router.lifespan_context(api.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app), base_url="http://test"
            ) as client,
        ):
            expected = {str(value) for value in ids.values()}
            response = await client.get("/api/nodes", params={"limit": 20})
            assert expected <= {node["gid"] for node in response.json()["items"]}
            json.dumps(response.json(), allow_nan=False)
            for gid in expected:
                detail = (await client.get(f"/api/nodes/{gid}")).json()
                assert detail["node"]["gid"] == gid
                json.dumps(detail, allow_nan=False)
                graph = (await client.get("/api/graph", params={"gid": gid})).json()
                assert gid in {node["gid"] for node in graph["nodes"]}
                json.dumps(graph, allow_nan=False)
            response = await client.get("/api/exports/nodes_roles.csv")
            assert response.status_code == 200
            csv_ids = {row["gid"] for row in csv.DictReader(io.StringIO(response.text))}
            assert expected <= csv_ids

    asyncio.run(check())


def test_api_export_remains_on_its_snapshot_during_external_recalculation(
    sample_data: Path, tmp_path: Path, monkeypatch
):
    out = tmp_path / "out"
    monkeypatch.setattr(api, "DATA_DIR", sample_data)
    monkeypatch.setattr(api, "OUT_DIR", out)

    async def check():
        async with (
            api.app.router.lifespan_context(api.app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api.app), base_url="http://test"
            ) as client,
        ):
            assert not out.exists()
            before = (await client.get("/api/exports/nodes_roles.csv")).content
            original_sum = (await client.get("/api/summary")).json()["sum_kzt"]
            edges_path = sample_data / "edges.parquet"
            tx_path = sample_data / "transactions.parquet"
            edges = pd.read_parquet(edges_path)
            tx = pd.read_parquet(tx_path)
            edges.loc[0, "sum_kzt"] += 100
            tx.loc[0, "sum_kzt"] += 100
            edges.to_parquet(edges_path, index=False)
            tx.to_parquet(tx_path, index=False)
            analyze(sample_data, out)
            assert (out / "nodes_roles.csv").read_bytes() != before
            assert (await client.get("/api/exports/nodes_roles.csv")).content == before
            assert (await client.get("/api/summary")).json()["sum_kzt"] == original_sum

    asyncio.run(check())
