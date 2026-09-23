# API v1 — Граф денег

Все основные маршруты начинаются с `/api`. Идентификаторы `gid` передаются строкой десятичного int64, чтобы клиент не терял точность. Суммы — KZT; score от 0 до 1. Неопределённая метрика кодируется `null`, не NaN/Infinity. API один раз рассчитывает снимок при старте; маршруты чтения и экспорта используют его из памяти и повторно не пересчитывают данные. Ошибка возвращается как `{"detail":"понятное сообщение"}`.

## Маршруты

- `GET /health` и `/api/health`: `{status:"ok"|"not_ready",ready:boolean,detail?:string}`.
- `GET /api/summary`: количество узлов, рёбер, транзакций, seed, кластеров, компонент, изолятов и boundary; общая сумма, период, время расчёта, `role_counts` и предупреждения набора.
- `GET /api/nodes?q=&role=&cluster_id=&limit=100&offset=0`: `{items:Node[],total,limit,offset}`. `q` — подстрока `gid`; сортировка по убыванию приоритета, затем по числовому `gid`; `limit` от 1 до 500.
- `GET /api/nodes/{gid}`: `{node:Node,incoming:Link[],outgoing:Link[],warnings:string[],next_steps:string[]}`. Возвращает все непосредственные связи; отсутствующий узел — 404.
- `GET /api/clusters`: `{items:Cluster[]}`.
- `GET /api/graph?gid=&cluster_id=&limit=120`: ограниченный подграф вокруг `gid`, выбранного кластера или обзор приоритетных узлов. `limit` от 1 до 300; `gid` включается в ответ. Возвращает `{nodes,edges,truncated,total_nodes,total_edges}`; рёбра сохраняют исходное направление и включаются, когда оба конца присутствуют в ответе.
- `GET /api/exports/{filename}`: скачивание `nodes_roles.csv`, `clusters.csv` или `top_nodes.csv`; прочие имена — 404. Байты формируются из того же снимка в памяти, что и JSON API.

## Объекты

```text
Node = {
  gid:string, role:string, role_score:number, cluster_id:number,
  priority_score:number, priority_breakdown:PriorityBreakdown[],
  priority_factor:number, priority_reason:string, evidence:string,
  depth:number, is_seed:boolean, boundary:boolean, component_id:number,
  in_degree:number, out_degree:number, in_kzt:number, out_kzt:number,
  in_tx:number, out_tx:number, pass_through:number|null,
  in_concentration:number, out_concentration:number, largest_out_share:number,
  pagerank:number, seed_source_count:number, seed_paths:string[][],
  collecting_branches:number, outgoing_communities:number
}
PriorityBreakdown = {label:string,value:number,normalized:number,weight:number}
Edge = {src:string,dst:string,sum_kzt:number,n_tx:number}
Link = Edge & {counterparty_gid:string,role:string}
Cluster = {cluster_id:number,n_nodes:number,n_seed:number,
           sum_kzt_internal:number,top_gids:string[],hypothesis:string}
```

`seed_source_count` считает различные seed, связанные с узлом путём по рёбрам к строго большей глубине; собственный путь seed к себе не включается, поэтому у seed значение `0`. `seed_paths` содержит до трёх кратчайших примеров; равные по длине варианты разрешаются лексикографически по числовой последовательности `gid`. Пути показывают достижимость, не атрибутируют конкретные средства и не задают хронологию.

`collecting_branches` — число непосредственных входящих соседей с формой `collector_shape`: не seed, не boundary depth=4, не менее двух входящих соседей, положительный входящий оборот и отношение `out_kzt / in_kzt ≤ 0,8`. Эта форма рассчитывается по исходным признакам независимо от первичной роли и без ограничения глубины предшественника. `outgoing_communities` — количество кластеров исходящих соседей. `largest_out_share` — доля исходящей суммы, пришедшаяся на крупнейшего непосредственного получателя; она используется в объяснении приоритета, но не меняет CSV-схему или сам score.

Узел может иметь предупреждение, что наблюдаемый выход превышает вход: вневыборочные поступления и остаток до периода неизвестны. Дополнительные предупреждения появляются для seed с неполными входами и для boundary depth=4. Английские значения ролей и схемы полей остаются стабильными; интерфейс даёт русские подписи. PageRank — справочное поле; приоритеты и роли не являются вероятностью виновности.

## Запуск

CLI: `uv run python -m backend.pipeline --data data --out out`. Он публикует три обычных CSV в `out/`, заменяя каждый файл отдельно через временный файл. Это не групповая транзакция для набора из трёх CSV.

Локальный API: `uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000`. При старте используется общая функция анализа с записью `write=False`; API формирует CSV-ответы из байтов своего in-memory snapshot и не пишет их в host `out/`. Production frontend FastAPI обслуживает из `frontend/dist`; путь можно настроить через `MONEY_GRAPH_STATIC`. Переменные `MONEY_GRAPH_DATA`, `MONEY_GRAPH_OUT`, `MONEY_GRAPH_STATIC` читаются из окружения процесса; `.env.example` автоматически не загружается.
