"""Read-only API and production SPA for one calculated graph snapshot."""

from __future__ import annotations

import mimetypes
import os
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from .pipeline import Snapshot, analyze

DATA_DIR = Path(os.getenv("MONEY_GRAPH_DATA", "data"))
OUT_DIR = Path(os.getenv("MONEY_GRAPH_OUT", "out"))
STATIC_DIR = Path(os.getenv("MONEY_GRAPH_STATIC", "frontend/dist"))
EXPORTS = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.snapshot = analyze(DATA_DIR, OUT_DIR)
        app.state.error = None
    except Exception as exc:  # noqa: BLE001 - health remains available after any startup failure
        app.state.snapshot = None
        app.state.error = str(exc)
    yield


app = FastAPI(title="Граф денег", lifespan=lifespan)


def snapshot() -> Snapshot:
    result = getattr(app.state, "snapshot", None)
    if result is None:
        raise HTTPException(
            status_code=503, detail=getattr(app.state, "error", "Данные ещё не рассчитаны")
        )
    return result


@app.get("/api/health")
@app.get("/health", include_in_schema=False)
async def health():
    ready = getattr(app.state, "snapshot", None) is not None
    result = {"status": "ok" if ready else "not_ready", "ready": ready}
    if not ready:
        result["detail"] = getattr(app.state, "error", "Данные ещё не рассчитаны")
    return result


@app.get("/api/summary")
async def summary():
    return snapshot().summary


@app.get("/api/nodes")
async def nodes(
    q: str = "",
    role: str | None = None,
    cluster_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    result = snapshot().nodes
    if q:
        result = [n for n in result if q in n["gid"]]
    if role:
        result = [n for n in result if n["role"] == role]
    if cluster_id is not None:
        result = [n for n in result if n["cluster_id"] == cluster_id]
    return {
        "items": result[offset : offset + limit],
        "total": len(result),
        "limit": limit,
        "offset": offset,
    }


def _node(gid: str) -> dict:
    if not (gid.isdecimal() or (gid.startswith("-") and gid[1:].isdecimal())):
        raise HTTPException(status_code=404, detail="Узел не найден")
    node = next((n for n in snapshot().nodes if n["gid"] == gid), None)
    if node is None:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return node


@app.get("/api/nodes/{gid}")
async def node_detail(gid: str):
    node = _node(gid)
    by_gid = {n["gid"]: n for n in snapshot().nodes}
    incoming = [
        dict(edge, counterparty_gid=edge["src"], role=by_gid[edge["src"]]["role"])
        for edge in snapshot().edges
        if edge["dst"] == gid
    ]
    outgoing = [
        dict(edge, counterparty_gid=edge["dst"], role=by_gid[edge["dst"]]["role"])
        for edge in snapshot().edges
        if edge["src"] == gid
    ]
    warnings = []
    if node["in_degree"] + node["out_degree"] == 0:
        next_steps = [
            "В выборке нет связей; запросить полную историю переводов, прежде чем формировать структурную гипотезу."
        ]
    else:
        next_steps = [
            "Проверить участников и назначение крупнейших связанных переводов по внутренним банковским данным."
        ]
    if node["boundary"]:
        warnings.append("Узел на границе 4-го колена: дальнейшие исходящие переводы не выгружены.")
        next_steps.append("Запросить исходящие переводы за пределами 4-го колена.")
    if node["is_seed"]:
        warnings.append(
            "Входящие переводы seed вне исходящей выборки неизвестны; баланс и коэффициент пропуска не определяются."
        )
        next_steps.append("Запросить полную историю входящих переводов этого исходного клиента.")
    if node["role"] == "consolidator":
        next_steps.append(
            "Проверить источники поступлений от разных плательщиков и следующие переводы."
        )
    elif node["role"] == "distributor":
        next_steps.append("Проверить связь между получателями веерной рассылки.")
    elif node["role"] == "transit":
        next_steps.append(
            "Сопоставить даты входящих и исходящих переводов для проверки скорости транзита."
        )
    return {
        "node": node,
        "incoming": incoming,
        "outgoing": outgoing,
        "warnings": warnings,
        "next_steps": next_steps,
    }


@app.get("/api/clusters")
async def clusters():
    return {"items": snapshot().clusters}


@app.get("/api/graph")
async def graph(
    gid: str | None = None, cluster_id: int | None = None, limit: int = Query(120, ge=1, le=300)
):
    snap = snapshot()
    if gid is not None:
        _node(gid)
        selected = {gid}
        for edge in snap.edges:
            if edge["src"] == gid:
                selected.add(edge["dst"])
            if edge["dst"] == gid:
                selected.add(edge["src"])
        candidates = [n for n in snap.nodes if n["gid"] in selected]
        kept = [next(n for n in candidates if n["gid"] == gid)]
        kept.extend(n for n in candidates if n["gid"] != gid)
        kept = kept[:limit]
    elif cluster_id is not None:
        candidates = [n for n in snap.nodes if n["cluster_id"] == cluster_id]
        kept = candidates[:limit]
    else:
        candidates = snap.nodes
        kept = candidates[:limit]
    candidates_gids = {n["gid"] for n in candidates}
    total_edges = sum(
        edge["src"] in candidates_gids and edge["dst"] in candidates_gids for edge in snap.edges
    )
    kept_gids = {n["gid"] for n in kept}
    edges = [edge for edge in snap.edges if edge["src"] in kept_gids and edge["dst"] in kept_gids]
    return {
        "nodes": kept,
        "edges": edges,
        "truncated": len(kept) < len(candidates),
        "total_nodes": len(candidates),
        "total_edges": total_edges,
    }


@app.get("/api/exports/{filename}")
async def export(filename: str):
    if filename not in EXPORTS:
        raise HTTPException(status_code=404, detail="Файл выгрузки не найден")
    target = snapshot().output_dir / filename
    if not target.is_file():
        raise HTTPException(status_code=503, detail="Выгрузка ещё не создана")
    return Response(
        target.read_bytes(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api")
@app.get("/api/{path:path}")
async def unknown_api(path: str = ""):
    raise HTTPException(status_code=404, detail="Маршрут API не найден")


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    root = STATIC_DIR.resolve()
    requested = (root / path).resolve()
    if requested.is_file() and requested.is_relative_to(root):
        return Response(
            requested.read_bytes(),
            media_type=mimetypes.guess_type(requested.name)[0] or "application/octet-stream",
        )
    index = root / "index.html"
    if index.is_file() and not path.startswith("api/"):
        return HTMLResponse(index.read_text(encoding="utf-8"))
    message = getattr(app.state, "error", None)
    if message:
        return HTMLResponse(
            f"<h1>Граф денег</h1><p>Данные не готовы: {escape(message)}</p>", status_code=503
        )
    return HTMLResponse(
        "<h1>Граф денег</h1><p>Соберите frontend, чтобы открыть интерфейс.</p>", status_code=503
    )
