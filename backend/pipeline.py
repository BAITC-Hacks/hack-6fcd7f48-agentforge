"""Deterministic, local analysis of the organizer's parquet files."""

from __future__ import annotations

import argparse
import math
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import networkx as nx
import pandas as pd

ROLE_COLUMNS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
CLUSTER_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]


@dataclass
class Snapshot:
    nodes: list[dict]
    edges: list[dict]
    clusters: list[dict]
    top: list[dict]
    summary: dict
    output_dir: Path
    exports: dict[str, bytes]


def _read(data_dir: Path, filename: str, required: set[str]) -> pd.DataFrame:
    path = data_dir / filename
    if not path.is_file():
        raise ValueError(f"Нет файла {path}; нужны три parquet в каталоге данных")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать {path}: {exc}") from exc
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"В {filename} отсутствуют колонки: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError(f"{filename} пуст")
    if frame[list(required)].isna().any().any():
        raise ValueError(f"{filename}: обязательные поля содержат null")
    return frame


def _integer(frame: pd.DataFrame, column: str, name: str, minimum: int | None = None) -> None:
    values = frame[column]
    if not pd.api.types.is_integer_dtype(values.dtype) or pd.api.types.is_bool_dtype(values.dtype):
        raise ValueError(f"{name}.{column} должен иметь целочисленный тип int64")
    if (values < -(2**63)).any() or (values > 2**63 - 1).any():
        raise ValueError(f"{name}.{column} выходит за диапазон int64")
    if minimum is not None and (values < minimum).any():
        raise ValueError(f"{name}.{column} должен быть не меньше {minimum}")


def _money(frame: pd.DataFrame, name: str) -> None:
    values = frame["sum_kzt"]
    if not pd.api.types.is_numeric_dtype(values.dtype) or pd.api.types.is_bool_dtype(values.dtype):
        raise ValueError(f"{name}.sum_kzt должен иметь числовой тип")
    if not values.map(math.isfinite).all() or (values <= 0).any():
        raise ValueError(f"{name}.sum_kzt должен содержать конечные положительные суммы")
    frame["sum_kzt"] = values.astype("float64")
    if not frame["sum_kzt"].map(math.isfinite).all():
        raise ValueError(f"{name}.sum_kzt выходит за диапазон float64")


def _finite_total(values, label: str) -> float:
    try:
        total = math.fsum(float(value) for value in values)
    except OverflowError as exc:
        raise ValueError(f"{label}: сумма выходит за числовой диапазон") from exc
    if not math.isfinite(total):
        raise ValueError(f"{label}: сумма выходит за числовой диапазон")
    return total


def _dates(frame: pd.DataFrame) -> None:
    values = frame["date"]
    if not pd.api.types.is_datetime64_any_dtype(values.dtype):
        for value in values:
            if isinstance(value, str):
                try:
                    date.fromisoformat(value)
                except ValueError:
                    try:
                        datetime.fromisoformat(value)
                    except ValueError as exc:
                        raise ValueError("transactions.date должен содержать ISO даты") from exc
            elif not isinstance(value, date):
                raise ValueError(  # noqa: TRY004 - all input validation errors are ValueError
                    "transactions.date должен содержать даты, а не числа"
                )
    try:
        frame["date"] = pd.to_datetime(values, errors="raise", format="mixed")
    except (TypeError, ValueError) as exc:
        raise ValueError("transactions.date содержит неверную дату") from exc


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes = _read(data_dir, "nodes.parquet", {"gid", "depth", "is_seed"})
    edges = _read(data_dir, "edges.parquet", {"src", "dst", "sum_kzt", "n_tx", "depth"})
    tx = _read(data_dir, "transactions.parquet", {"src", "dst", "date", "sum_kzt"})
    _integer(nodes, "gid", "nodes")
    _integer(nodes, "depth", "nodes", 0)
    for col in ("src", "dst", "n_tx", "depth"):
        _integer(edges, col, "edges", 1 if col in ("n_tx", "depth") else None)
    for col in ("src", "dst"):
        _integer(tx, col, "transactions")
    if nodes.gid.duplicated().any():
        raise ValueError("nodes.gid содержит дубликаты")
    if edges.duplicated(["src", "dst"]).any():
        raise ValueError("edges содержит повторные пары src,dst")
    if nodes.is_seed.map(type).ne(bool).any() and not pd.api.types.is_bool_dtype(nodes.is_seed):
        raise ValueError("nodes.is_seed должен быть bool")
    if ((nodes.is_seed & (nodes.depth != 0)) | (~nodes.is_seed & (nodes.depth == 0))).any():
        raise ValueError("nodes: depth=0 должен совпадать с is_seed")
    if (nodes.depth > 4).any() or (edges.depth > 4).any():
        raise ValueError("depth должен быть в диапазоне 0..4 для узлов и 1..4 для рёбер")
    gids = set(nodes.gid.astype(int))
    for name, frame in (("edges", edges), ("transactions", tx)):
        for col in ("src", "dst"):
            if not set(frame[col].astype(int)).issubset(gids):
                raise ValueError(f"{name}.{col}: найден gid без строки в nodes")
    _money(edges, "edges")
    _money(tx, "transactions")
    _finite_total(edges.sum_kzt, "edges.sum_kzt")
    _finite_total(tx.sum_kzt, "transactions.sum_kzt")
    incoming = edges.groupby("dst").sum_kzt.sum()
    outgoing = edges.groupby("src").sum_kzt.sum()
    observed_volume = incoming.add(outgoing, fill_value=0)
    if not observed_volume.map(math.isfinite).all():
        raise ValueError(
            "edges.sum_kzt: сумма входящих и исходящих по узлу выходит за числовой диапазон"
        )
    _dates(tx)
    sums = tx.groupby(["src", "dst"], sort=True).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size")
    )
    aggregate = edges.set_index(["src", "dst"])[["sum_kzt", "n_tx"]].sort_index()
    if not sums.sum_kzt.map(math.isfinite).all():
        raise ValueError("transactions.sum_kzt: сумма по паре выходит за числовой диапазон")
    if not sums.index.equals(aggregate.index) or not (sums.n_tx == aggregate.n_tx).all():
        raise ValueError("edges и transactions: пары или количества транзакций не совпадают")
    if not ((sums.sum_kzt - aggregate.sum_kzt).abs() <= 0.01).all():
        raise ValueError("edges и transactions: агрегированные суммы не совпадают")
    return nodes, edges, tx


def _scale(value: float, threshold: float) -> float:
    return min(1.0, max(0.0, value / threshold))


def _round(value: float) -> float:
    return round(float(value), 6)


def _pagerank(graph: nx.DiGraph, damping: float = 0.85) -> dict[int, float]:
    """Weighted PageRank by power iteration, without an extra scipy dependency."""
    vertices = sorted(graph)
    count = len(vertices)
    rank = {gid: 1 / count for gid in vertices}
    weight_out = {gid: sum(edge["weight"] for edge in graph.succ[gid].values()) for gid in vertices}
    for _ in range(200):
        dangling = sum(rank[gid] for gid in vertices if weight_out[gid] == 0)
        next_rank = {gid: (1 - damping + damping * dangling) / count for gid in vertices}
        for src in vertices:
            if weight_out[src]:
                for dst, edge in graph.succ[src].items():
                    next_rank[dst] += damping * rank[src] * (edge["weight"] / weight_out[src])
        delta = sum(abs(next_rank[gid] - rank[gid]) for gid in vertices)
        rank = next_rank
        if delta < 1e-10:
            break
    return rank


def _build_graph(
    nodes_df: pd.DataFrame, edges_df: pd.DataFrame
) -> tuple[nx.DiGraph, list[set[int]], list[set[int]]]:
    """Build the directed network and stable community/component ordering."""
    graph = nx.DiGraph()
    for row in nodes_df.itertuples(index=False):
        graph.add_node(int(row.gid))
    for row in edges_df.itertuples(index=False):
        graph.add_edge(int(row.src), int(row.dst), weight=float(row.sum_kzt), n_tx=int(row.n_tx))
    projection = nx.Graph()
    projection.add_nodes_from(graph)
    for src, dst, attrs in graph.edges(data=True):
        if projection.has_edge(src, dst):
            projection[src][dst]["weight"] += attrs["weight"]
        else:
            projection.add_edge(src, dst, weight=attrs["weight"])
    communities = list(nx.community.louvain_communities(projection, weight="weight", seed=42))
    communities.sort(key=lambda group: min(group))
    components = sorted(nx.weakly_connected_components(graph), key=lambda group: min(group))
    return graph, communities, components


def _seed_paths(graph: nx.DiGraph, nodes_df: pd.DataFrame) -> dict[int, dict[int, list[str]]]:
    """One stable shortest path per seed, using only edges to a greater depth.

    This measures observed reachability, not the provenance of particular money.
    The depth restriction prevents cycles from spreading seed labels backwards.
    """
    info = nodes_df.set_index("gid")
    paths: dict[int, dict[int, list[str]]] = {}
    for gid in sorted(graph, key=lambda node: (int(info.at[node, "depth"]), node)):
        paths[gid] = {}
        if bool(info.at[gid, "is_seed"]):
            paths[gid][gid] = [str(gid)]
            continue
        for parent in sorted(graph.predecessors(gid)):
            if info.at[parent, "depth"] >= info.at[gid, "depth"]:
                continue
            for seed, prefix in paths[parent].items():
                candidate = prefix + [str(gid)]
                previous = paths[gid].get(seed)
                if previous is None or (len(candidate), tuple(map(int, candidate))) < (
                    len(previous),
                    tuple(map(int, previous)),
                ):
                    paths[gid][seed] = candidate
    return paths


def _number(value: float, places: int = 0) -> str:
    """Readable Russian numbers, without locale-dependent process settings."""
    result = f"{value:,.{places}f}".replace(",", " ").replace(".", ",")
    return result.rstrip("0").rstrip(",") if places else result


def _money_text(value: float) -> str:
    return f"{_number(value, 2)} ₸"


def _node_records(
    graph: nx.DiGraph,
    nodes_df: pd.DataFrame,
    communities: list[set[int]],
    components: list[set[int]],
) -> list[dict]:
    """Calculate observable metrics and the ordered, explainable role rules."""
    cluster_of = {gid: index + 1 for index, group in enumerate(communities) for gid in group}
    component_of = {gid: index + 1 for index, group in enumerate(components) for gid in group}
    pagerank = _pagerank(graph)
    node_info = nodes_df.set_index("gid")
    seed_paths = _seed_paths(graph, nodes_df)
    in_weights = dict(graph.in_degree(weight="weight"))
    out_weights = dict(graph.out_degree(weight="weight"))
    # Collector shape is independent of the final primary role, so loops do not
    # make role assignment recursive. Depth is a shortest hop, not a time order.
    collectors = {
        gid
        for gid in graph
        if not bool(node_info.at[gid, "is_seed"])
        and int(node_info.at[gid, "depth"]) < 4
        and graph.in_degree(gid) >= 2
        and in_weights[gid] > 0
        and out_weights[gid] / in_weights[gid] <= 0.8
    }
    records: list[dict] = []
    for gid in sorted(graph):
        pred = graph.pred[gid]
        succ = graph.succ[gid]
        incoming = list(pred.values())
        outgoing = list(succ.values())
        in_kzt = sum(v["weight"] for v in incoming)
        out_kzt = sum(v["weight"] for v in outgoing)
        in_tx = sum(v["n_tx"] for v in incoming)
        out_tx = sum(v["n_tx"] for v in outgoing)
        in_degree, out_degree = len(pred), len(succ)
        depth = int(node_info.at[gid, "depth"])
        is_seed = bool(node_info.at[gid, "is_seed"])
        boundary = depth == 4
        pass_through = None if is_seed or in_kzt <= 0 else out_kzt / in_kzt
        if pass_through is not None and not math.isfinite(pass_through):
            raise ValueError(
                f"gid {gid}: отношение исходящих к входящим выходит за числовой диапазон"
            )
        in_concentration = sum((v["weight"] / in_kzt) ** 2 for v in incoming) if in_kzt else 0.0
        out_concentration = sum((v["weight"] / out_kzt) ** 2 for v in outgoing) if out_kzt else 0.0
        observed_paths = [path for seed, path in seed_paths[gid].items() if seed != gid]
        observed_paths.sort(key=lambda path: (len(path), tuple(map(int, path))))
        seed_source_count = len(observed_paths)
        collecting_branches = sum(parent in collectors for parent in pred)
        outgoing_communities = len({cluster_of[recipient] for recipient in succ})
        # Ordered rules: the first matching structural hypothesis is the primary role.
        if not is_seed and not boundary and collecting_branches >= 2 and out_degree >= 2:
            role = "coordinator"
            confidence = (
                0.55
                + 0.25 * _scale(collecting_branches, 5)
                + 0.20 * _scale(in_degree + out_degree, 20)
            )
            evidence = (
                f"Гипотеза координации: узлов сбора на входе — {collecting_branches}; "
                f"получателей — {out_degree}."
            )
        elif gid in collectors:
            role = "consolidator"
            confidence = 0.50 + 0.30 * _scale(in_degree, 10) + 0.20 * (1 - pass_through)
            evidence = (
                f"Плательщиков — {in_degree}; дальше отправлено {_number(pass_through * 100, 1)}% входа. "
                f"В выборке получено {_money_text(in_kzt)}."
            )
        elif out_degree >= 5 and out_degree >= 2 * max(in_degree, 1):
            role = "distributor"
            confidence = 0.55 + 0.3 * _scale(out_degree, 40) + 0.15 * (1 - out_concentration)
            evidence = (
                f"Признаки распределения: получателей — {out_degree}; выход {_money_text(out_kzt)}."
            )
        elif (
            pass_through is not None
            and in_degree > 0
            and out_degree > 0
            and 0.8 <= pass_through <= 1.2
        ):
            role = "transit"
            confidence = (
                0.55
                + 0.3 * (1 - abs(pass_through - 1) / 0.2)
                + 0.15 * _scale(in_degree + out_degree, 10)
            )
            evidence = (
                f"Признаки транзита: вход {_money_text(in_kzt)}; дальше отправлено "
                f"{_number(pass_through * 100, 1)}% наблюдаемого входа."
            )
        elif in_degree > 0 and out_degree == 0 and not boundary and not is_seed:
            role = "terminal"
            confidence = 0.55 + 0.25 * _scale(in_degree, 5) + 0.2 * _scale(in_kzt, 1_000_000)
            evidence = (
                f"Получено {_money_text(in_kzt)}; плательщиков — {in_degree}; "
                "в выборке исходящих нет."
            )
        else:
            role = "peripheral"
            confidence = 0.5 + 0.2 * _scale(in_degree + out_degree, 4)
            if boundary and out_degree == 0:
                evidence = f"Граница 4-го колена: вход {_money_text(in_kzt)}; дальнейшие переводы неизвестны."
            elif is_seed:
                evidence = f"Исходный клиент: {in_degree} входящих, {out_degree} исходящих связей; входящая выборка неполна."
            else:
                evidence = (
                    f"Роль не определена: плательщиков — {in_degree}, получателей — {out_degree}."
                )
        if pass_through is not None and pass_through > 1:
            if role == "transit":
                evidence += " Баланс неполон."
            elif _number(pass_through, 2) == "1":
                evidence += " Выход немного выше входа; баланс неполон."
            else:
                evidence += f" Выход выше входа; отношение {_number(pass_through, 2)}. Баланс неполон."
        if boundary:
            confidence = min(confidence, 0.75)
            if "Граница" not in evidence:
                evidence += " Граница depth=4: продолжение неизвестно."
        if is_seed:
            confidence = min(confidence, 0.85)
            if "входящ" not in evidence:
                evidence += " У seed входящие неполны."
        rec = {
            "gid": str(gid),
            "role": role,
            "role_score": _round(confidence),
            "cluster_id": cluster_of[gid],
            "priority_score": 0.0,
            "evidence": evidence[:200],
            "depth": depth,
            "is_seed": is_seed,
            "in_degree": in_degree,
            "out_degree": out_degree,
            "in_kzt": _round(in_kzt),
            "out_kzt": _round(out_kzt),
            "in_tx": in_tx,
            "out_tx": out_tx,
            "pagerank": _round(pagerank[gid]),
            "pass_through": _round(pass_through) if pass_through is not None else None,
            "in_concentration": _round(in_concentration),
            "out_concentration": _round(out_concentration),
            "largest_out_share": _round(max((v["weight"] / out_kzt for v in outgoing), default=0)),
            "boundary": boundary,
            "component_id": component_of[gid],
            "seed_source_count": seed_source_count,
            "seed_paths": observed_paths[:3],
            "collecting_branches": collecting_branches,
            "outgoing_communities": outgoing_communities,
        }
        records.append(rec)
    return records


def _prioritize(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rank observable convergence beyond known seeds, without a role bonus."""
    for record in records:
        seeds, degree = record["seed_source_count"], record["in_degree"]
        volume, concentration = record["in_kzt"], record["out_concentration"]
        forwarding = concentration * (1 - 1 / degree) if degree >= 2 and record["out_degree"] else 0
        record["priority_breakdown"] = [
            {"label": label, "value": value, "normalized": normalized, "weight": weight}
            for label, value, normalized, weight in (
                ("Пути от разных исходных клиентов", seeds, seeds / (seeds + 1), 0.35),
                ("Непосредственные плательщики", degree, degree / (degree + 3), 0.30),
                ("Входящий оборот, ₸", volume, volume / (volume + 500_000), 0.20),
                ("Концентрация пересылки", concentration, forwarding, 0.15),
            )
        ]
        if record["is_seed"]:
            factor, reason = 0.5, "Уже известный исходный клиент: коэффициент 0,5; входы неполны."
        elif record["boundary"]:
            factor, reason = (
                0.85,
                "Граница обхода: коэффициент 0,85; дальнейшие переводы неизвестны.",
            )
        else:
            factor, reason = 1.0, "Не исходный клиент и не граница обхода: коэффициент 1."
        record["priority_factor"] = factor
        record["priority_reason"] = reason
        record["priority_score"] = _round(
            factor
            * sum(item["normalized"] * item["weight"] for item in record["priority_breakdown"])
        )
    records.sort(key=lambda n: (-n["priority_score"], int(n["gid"])))
    top = [
        {
            "rank": i,
            "gid": n["gid"],
            "role": n["role"],
            "priority_score": n["priority_score"],
            "why": (
                f"{n['evidence']} Исходных клиентов с путями до узла — {n['seed_source_count']}. "
                + (
                    f"Из отправленного {_number(n['largest_out_share'] * 100, 1)}% "
                    "ушло одному получателю. "
                    if n["out_degree"] > 0
                    else ""
                )
                + f"{n['priority_reason']} Пути не доказывают происхождение конкретных денег."
            ),
        }
        for i, n in enumerate(records[:100], 1)
    ]
    return records, top


def _cluster_records(
    graph: nx.DiGraph, communities: list[set[int]], records: list[dict]
) -> list[dict]:
    """Summarize internal flows and cautious structural hypotheses."""
    clusters = []
    by_gid = {int(n["gid"]): n for n in records}
    role_label = {
        "coordinator": "координация",
        "consolidator": "сбор средств",
        "distributor": "распределение средств",
        "transit": "транзит",
        "terminal": "получение без наблюдаемого выхода",
        "peripheral": "периферия",
    }
    for index, group in enumerate(communities, 1):
        ranked = sorted(group, key=lambda gid: (-by_gid[gid]["priority_score"], gid))
        n_seed = sum(by_gid[gid]["is_seed"] for gid in group)
        internal = sum(
            v["weight"] for u, vtx, v in graph.edges(data=True) if u in group and vtx in group
        )
        counts = pd.Series([by_gid[gid]["role"] for gid in group]).value_counts()
        primary = counts.index[0]
        n_collect = int(counts.get("consolidator", 0))
        n_distribute = int(counts.get("distributor", 0))
        n_transit = int(counts.get("transit", 0))
        if len(group) == 1 and graph.degree[next(iter(group))] == 0:
            hypothesis = "Изолированный узел: в выборке нет связей; назначение определить нельзя."
        else:
            if n_collect and n_distribute:
                purpose = "возможная связка сбора и распределения"
            elif n_collect:
                purpose = "возможный участок сбора"
            elif n_distribute:
                purpose = "возможный участок распределения"
            elif n_transit:
                purpose = "возможный транзитный участок"
            else:
                purpose = "назначение по структуре не определяется"
            hypothesis = (
                f"Гипотеза: {purpose}. Исходных узлов: {n_seed}; внутренний оборот "
                f"{_money_text(internal)}. Кандидаты: сбор {n_collect}, распределение "
                f"{n_distribute}, транзит {n_transit}. Чаще всего: {role_label[primary]} "
                f"(узлов — {int(counts.iloc[0])})."
            )
        clusters.append(
            {
                "cluster_id": index,
                "n_nodes": len(group),
                "n_seed": n_seed,
                "sum_kzt_internal": _round(internal),
                "top_gids": [str(gid) for gid in ranked[:5]],
                "hypothesis": hypothesis,
            }
        )
    return clusters


def _csv_exports(records: list[dict], clusters: list[dict], top: list[dict]) -> dict[str, bytes]:
    tables = {
        "nodes_roles.csv": pd.DataFrame(records)[ROLE_COLUMNS],
        "clusters.csv": pd.DataFrame(clusters).assign(
            top_gids=lambda df: df.top_gids.map(lambda gids: ",".join(gids))
        )[CLUSTER_COLUMNS],
        "top_nodes.csv": pd.DataFrame(top)[TOP_COLUMNS],
    }
    return {
        name: table.to_csv(index=False, lineterminator="\n").encode("utf-8")
        for name, table in tables.items()
    }


def _publish_csv(out_dir: Path, exports: dict[str, bytes]) -> None:
    """Publish ordinary CSV files; a failed write cannot truncate an existing file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in exports.items():
        staged = None
        try:
            with NamedTemporaryFile(dir=out_dir, prefix=f".{name}.", delete=False) as handle:
                staged = Path(handle.name)
                handle.write(content)
            os.replace(staged, out_dir / name)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)


def analyze(data_dir: Path, out_dir: Path, *, write: bool = True) -> Snapshot:
    start = time.perf_counter()
    nodes_df, edges_df, tx_df = load_data(data_dir)
    nodes_df = nodes_df.sort_values("gid").reset_index(drop=True)
    edges_df = edges_df.sort_values(["src", "dst"]).reset_index(drop=True)
    graph, communities, components = _build_graph(nodes_df, edges_df)
    records = _node_records(graph, nodes_df, communities, components)
    records, top = _prioritize(records)
    edge_records = [
        {
            "src": str(int(r.src)),
            "dst": str(int(r.dst)),
            "sum_kzt": _round(r.sum_kzt),
            "n_tx": int(r.n_tx),
        }
        for r in edges_df.itertuples(index=False)
    ]
    clusters = _cluster_records(graph, communities, records)
    role_counts = {
        role: sum(n["role"] == role for n in records)
        for role in (
            "consolidator",
            "transit",
            "distributor",
            "terminal",
            "coordinator",
            "peripheral",
        )
    }
    warnings = [
        "Граф построен только по исходящим переводам до 4-го колена; баланс и конечность потоков вне выборки неизвестны.",
        "У клиентов на depth=4 отсутствие исходящих — артефакт границы обхода.",
        "Входящие суммы seed могут быть занижены; отношение выхода ко входу для них не рассчитывается.",
        "Переводы ниже 5 000 KZT и внебанковские операции отсутствуют; роли — гипотезы, не доказательство виновности.",
    ]
    dates = pd.to_datetime(tx_df.date)
    summary = {
        "n_nodes": len(records),
        "n_edges": len(edge_records),
        "n_transactions": len(tx_df),
        "n_seeds": int(nodes_df.is_seed.sum()),
        "n_clusters": len(clusters),
        "n_components": len(components),
        "n_isolates": nx.number_of_isolates(graph),
        "n_boundary": int((nodes_df.depth == 4).sum()),
        "sum_kzt": _round(tx_df.sum_kzt.sum()),
        "period_start": str(dates.min().date()),
        "period_end": str(dates.max().date()),
        "elapsed_seconds": 0.0,
        "role_counts": role_counts,
        "warnings": warnings,
    }
    exports = _csv_exports(records, clusters, top)
    if write:
        _publish_csv(out_dir, exports)
    summary["elapsed_seconds"] = _round(time.perf_counter() - start)
    return Snapshot(records, edge_records, clusters, top, summary, out_dir, exports)


def main() -> None:
    parser = argparse.ArgumentParser(description="Рассчитать роли и кластеры графа денег")
    parser.add_argument("--data", type=Path, default=Path(os.getenv("MONEY_GRAPH_DATA", "data")))
    parser.add_argument("--out", type=Path, default=Path(os.getenv("MONEY_GRAPH_OUT", "out")))
    args = parser.parse_args()
    try:
        snapshot = analyze(args.data, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(
        f"Готово: {snapshot.summary['n_nodes']} узлов, {snapshot.summary['n_clusters']} кластеров, {snapshot.summary['elapsed_seconds']} с; CSV: {args.out}"
    )


if __name__ == "__main__":
    main()
