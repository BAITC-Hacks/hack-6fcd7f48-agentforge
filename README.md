# Граф денег

Инструмент для AML-аналитика: определить, какие узлы обезличенной сети переводов проверить в первую очередь и на каких численных основаниях.

**Текущий этап: подготовка окружения.** В этой версии зафиксированы зависимости Python и frontend, версия Python, безопасный пример переменных окружения и исключения локальных файлов. Пайплайн, API, интерфейс и проверки будут добавляться отдельными следующими коммитами.

## Подготовка окружения

Нужны Python 3.14.3, [uv](https://docs.astral.sh/uv/), Node.js 24 и npm. Проверенные версии инструментов: uv 0.12.16, Node.js 24.21.0, npm 11.19.0. Команды выполняются из корня репозитория:

```bash
uv sync --frozen
npm --prefix frontend ci
```

Python-зависимости закреплены в `uv.lock`, frontend-зависимости — в `frontend/package-lock.json`. Первая установка требует доступа к PyPI и npm registry. Платный API и ключи для основного сценария не предусмотрены.

Корневой `.env.example` содержит только локальные пути: `MONEY_GRAPH_DATA`, `MONEY_GRAPH_OUT`, `MONEY_GRAPH_STATIC`. Файлы `.env`, исходные данные и результаты расчёта исключены из Git.

## Выбранный кейс и следующий результат

Кейс HackAlem AI — [«Граф денег»](https://docs.google.com/document/d/1JPLU-G6R25Ge2hVaY2J9cqvrx7FGExj87XKwJPaMz3o/edit). План основной реализации:

1. Проверка трёх Parquet, направленный взвешенный граф, объяснимые роли и кластеры.
2. Три выгрузки: `nodes_roles.csv`, `clusters.csv`, `top_nodes.csv`.
3. Рабочий интерфейс с приоритетами, поиском любого gid, связями и основаниями выводов.

Архитектура: общий Python-пайплайн для CLI и FastAPI; API читает рассчитанный снимок; React и Cytoscape отображают ограниченную часть графа. В production FastAPI будет обслуживать API и собранный frontend на одном порту.

## Данные и ограничения

Официальные материалы: [README набора](https://drive.google.com/file/d/1ro-SiY042jv7De0h7tXBDyY8ZKdHz_US/view), [архив данных](https://drive.google.com/file/d/1yHdWaSb6gwPAUrqco-KrwR2U_YhzFQFT/view).

Данные предоставлены только для использования в рамках хакатона. Исходные Parquet и содержащие их выгрузки не публикуются в репозитории. Выборка охватывает исходящие внутрибанковские переводы за июль 2026 до четырёх колен, с порогом 5 000 KZT. Отсутствие исходящих у depth=4 не означает конечного получателя; входящие seed неполны. Роли будут гипотезами для проверки, scores — эвристическими оценками, не вероятностью виновности. Внешнее обогащение клиентов не используется.

## Зафиксированный стек

| Компонент | Версия | Лицензия / источник |
|---|---|---|
| FastAPI | 0.141.1 | MIT · [исходный код](https://github.com/fastapi/fastapi) |
| Pydantic | 2.13.5 | MIT · [исходный код](https://github.com/pydantic/pydantic) |
| Uvicorn | 0.53.0 | BSD-3-Clause · [исходный код](https://github.com/Kludex/uvicorn) |
| pandas | 2.3.3 | BSD-3-Clause · [исходный код](https://github.com/pandas-dev/pandas) |
| PyArrow | 24.0.0 | Apache-2.0 · [исходный код](https://github.com/apache/arrow) |
| NetworkX | 3.7 | BSD-3-Clause · [исходный код](https://github.com/networkx/networkx) |
| React / React DOM | 19.1.1 | MIT · [исходный код](https://github.com/facebook/react) |
| Cytoscape.js | 3.32.1 | MIT · [исходный код](https://github.com/cytoscape/cytoscape.js) |
| TypeScript | 5.9.2 | Apache-2.0 · [исходный код](https://github.com/microsoft/TypeScript) |
| Vite | 7.3.6 | MIT · [исходный код](https://github.com/vitejs/vite) |

Разработческие зависимости включают pytest, HTTPX, Ruff и ESLint; полный перечень версий находится в lock-файлах. Для разработки используются AI-агенты OpenAI Codex. Внешний LLM API внутри продукта не требуется.

## Происхождение репозитория

Официальный репозиторий команды AgentForge: `hack-6fcd7f48-agentforge`. Исходный README организаторов: «Hackathon team repository for AgentForge». Исходная история сохранена.
