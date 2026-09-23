# API v1 — Граф денег

Все пути начинаются с `/api`. gid передаётся строкой десятичного int64, чтобы браузер не терял точность. Все суммы в KZT, scores в [0,1]. Неопределённая метрика — null, никогда NaN/Infinity. API использует один рассчитанный снимок; GET не пересчитывает аналитику. Ошибки: `{"detail":"понятное сообщение"}`.

- `GET /health` (полный путь `/api/health`, также есть alias `/health`): `{status: "ok"|"not_ready", ready: boolean, detail?: string}`; доступен без данных.
- `GET /summary`: `{n_nodes,n_edges,n_transactions,n_seeds,n_clusters,n_components,n_isolates,n_boundary,sum_kzt,period_start,period_end,elapsed_seconds,role_counts: Record<string,number>,warnings: string[]}`.
- `GET /nodes?q=&role=&cluster_id=&limit=100&offset=0`: `{items: Node[],total,limit,offset}`. q — подстрока gid; порядок priority_score убывает, затем gid по числу возрастает. limit 1..500. role и cluster_id опциональны.
- `GET /nodes/{gid}`: `{node:Node,incoming:Link[],outgoing:Link[],warnings:string[],next_steps:string[]}`. Все непосредственные связи, 404 для отсутствующего gid.
- `GET /clusters`: `{items:Cluster[]}`.
- `GET /graph?gid=&cluster_id=&limit=120`: `{nodes:Node[],edges:Edge[],truncated:boolean,total_nodes:number,total_edges:number}`. Либо окрестность gid (сам узел и все непосредственные соседи), либо кластер, либо обзор приоритетных узлов. limit 1..300. gid всегда включён. total_* относятся к полной выборке до ограничения; edges содержит только связи между возвращёнными узлами. Все исходные направления сохранены.
- `GET /exports/{filename}`: CSV `nodes_roles.csv`, `clusters.csv` или `top_nodes.csv`, прочие имена — 404.

`Node = {gid:string,role:string,role_score:number,cluster_id:number,priority_score:number,evidence:string,depth:number,is_seed:boolean,in_degree:number,out_degree:number,in_kzt:number,out_kzt:number,in_tx:number,out_tx:number,pagerank:number,pass_through:number|null,in_concentration:number,out_concentration:number,boundary:boolean,component_id:number}`.

`Edge = {src:string,dst:string,sum_kzt:number,n_tx:number}`.
`Link = Edge & {counterparty_gid:string,role:string}`.
`Cluster = {cluster_id:number,n_nodes:number,n_seed:number,sum_kzt_internal:number,top_gids:string[],hypothesis:string}`.

Роли: consolidator, transit, distributor, terminal, coordinator, peripheral. Русские подписи определяются интерфейсом, значения CSV/API остаются английскими. Карточка и граф дают гипотезы; scores не являются вероятностью виновности. Граница depth=4 и неполнота входящих seed явно показаны.

Запуск CLI: `uv run python -m backend.pipeline --data data --out out`. API: `uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000`. На старте API единожды считает данные через общую логику и пишет согласованный набор результатов. Отсутствие данных оставляет health и понятную страницу ошибки доступными. Production frontend обслуживает FastAPI из `frontend/dist` (настраивается MONEY_GRAPH_STATIC).
