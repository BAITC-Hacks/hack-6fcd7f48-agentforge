# Архитектура

## Поток данных

```mermaid
flowchart LR
    P[Три Parquet-файла] --> V[Проверка типов, диапазонов и агрегатов]
    V --> G[Ориентированный граф потоков]
    G --> M[Степени, обороты, PageRank]
    M --> R[Роли и приоритет узлов]
    R --> C[Louvain и гипотезы кластеров]
    C --> S[Неизменяемый снимок]
    S --> CSV[Три CSV + ссылки на current]
    S --> API[FastAPI: snapshot API]
    API --> UI[React + Cytoscape]
```

## Компоненты

- `scripts/fetch_data.py` читает публичный архив организатора без cookies/account либо локальный ZIP, проверяет SHA-256 и сигнатуры Parquet, пишет `data/source.json`.
- `backend/pipeline.py` строго проверяет наличие входных файлов, колонки, целочисленные типы и int64 диапазон, числовые суммы и даты, seed/depth consistency, endpoints, уникальность узлов/рёбер и соответствие транзакционных пар, сумм и количества `edges`.
- Pipeline создаёт ориентированный `networkx.DiGraph`; рассчитывает степени, потоки, концентрации и weighted PageRank собственной power iteration; присваивает роли последовательными правилами; приоритет — по процентильным рангам; кластеризация — Louvain на взвешенной неориентированной проекции.
- На каждый запуск CSV записываются в `out/.snapshots/<id>`. После полной записи `out/current` атомарно переключается на новый снимок. Корневые `out/*.csv` — стабильные ссылки на файлы текущего снимка. Повторный расчёт на этих данных дал идентичные байты.
- `backend/app.py` при старте рассчитывает один снимок и отдаёт summary, список и карточку узла, кластер, ограниченный подграф и CSV. В карточке есть раскрываемый разбор оборота/связей/PageRank/веса роли и формулы приоритета. Основные пути начинаются с `/api`; `/health` сохранён как alias `/api/health`. API работает с тем же immutable snapshot, что и экспорт.
- `frontend/` содержит React/Cytoscape интерфейс: поиск числового `gid`, список приоритетов, фильтры роли и кластера, общий вид сети/кластер/окрестность узла, карточку с flows и warnings. Рёбра имеют стрелки; цвет показывает роль; доступен zoom/fit.

## Среда запуска

Подтверждённая ОС — Linux; файловая система должна поддерживать POSIX symlink. macOS и WSL не проверялись. Python 3.14.3, `uv` 0.12.16, Node.js 24.21.0, npm 11.19.0. Локальный Uvicorn рекомендуется привязывать к `127.0.0.1:8000`. Переменные `MONEY_GRAPH_DATA`, `MONEY_GRAPH_OUT`, `MONEY_GRAPH_STATIC` читаются из процесса; `.env.example` автоматически не загружается.

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
python3 scripts/fetch_data.py
uv run python -m backend.pipeline --data data --out out
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

В compose один сервис `money-graph`: port `127.0.0.1:8000:8000`, `data/` mounted read-only, `out/` writable. Fetch выполняется на host под Python 3.10+; Docker image содержит runtime, но загрузчик на host запускается отдельно.

```bash
python3 scripts/fetch_data.py
docker compose up --build -d --wait
```

## Проверенные результаты

Полный CLI wall time — 0,99 с, внутренний analysis — 0,510786 с на предоставленном наборе: 2 248 узлов, 3 119 рёбер, 4 840 транзакций, 81 seed, 91 кластер, 35 weak components (16 с рёбрами и 19 isolates), 444 boundary, 365 890 012,01 KZT. В чистой копии 24 теста прошли за 3,04 с; Ruff, frontend lint/typecheck/build и `npm audit` (0 vulnerabilities) — PASS. Docker Compose build и `up --wait` завершились успешно, сервис healthy. HTTP summary готов; все три CSV выгрузки вернули 200 с attachment и ожидаемыми заголовками, содержат 2 248 / 91 / 100 строк и побайтно совпадают со снимком. Браузер получил download event для каждого CSV; интерфейс проверен на ширинах 1440 и 390 px без горизонтального переполнения и ошибок console. В плотных окрестностях узлы и подписи могут пересекаться, поэтому читаемость графа требует дальнейшей работы над раскладкой и масштабом. Регрессионный тест проверяет обнаружение переполнения при агрегации экстремальных конечных сумм.

Зависимости, fetch, тесты, CLI, frontend build, Docker и браузерная проверка прошли в чистой локальной копии без `.git`, `data/out`, venv, node_modules и прежних кешей; это отчёт локальной приёмки, не результат удалённого запуска. Remote fresh clone и GitHub Actions ещё не подтверждены. После публикации смотреть [актуальный статус в Actions](../../../actions/workflows/verify.yml); конфигурация CI — [verify.yml](../.github/workflows/verify.yml).
