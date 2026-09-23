# Сторонние компоненты, источники и лицензии

Версии ниже сверены с `uv.lock`, установленными Python package metadata, `frontend/package-lock.json` и `frontend/node_modules/*/package.json` на 23 сентября 2026 года. `uv.lock` фиксирует версии и хеши дистрибутивов; npm lockfile — дерево пакетов. Указание лицензии основано на metadata компонента, а не является отдельным юридическим аудитом.

## Python: runtime и разработка

| Компонент | Версия для Python 3.14 | Назначение | Лицензия | Источник |
|---|---:|---|---|---|
| FastAPI | 0.141.1 | HTTP API | MIT | [GitHub](https://github.com/fastapi/fastapi) |
| Uvicorn | 0.53.0 | ASGI сервер | BSD-3-Clause | [GitHub](https://github.com/Kludex/uvicorn) |
| pandas | 2.3.3 | Табличная обработка | BSD-3-Clause | [GitHub](https://github.com/pandas-dev/pandas) |
| PyArrow | 24.0.0 | Чтение Parquet | Apache-2.0 | [GitHub](https://github.com/apache/arrow) |
| NetworkX | 3.7 | Граф и Louvain | BSD-3-Clause | [GitHub](https://github.com/networkx/networkx) |
| Pydantic | 2.13.5 | Типы и валидация FastAPI; явные response-model схемы не заданы | MIT | [GitHub](https://github.com/pydantic/pydantic) |
| pytest | 9.1.1 | Разработка и QA | MIT | [GitHub](https://github.com/pytest-dev/pytest) |
| HTTPX | 0.28.1 | API-тестирование | BSD-3-Clause | [GitHub](https://github.com/encode/httpx) |
| Ruff | 0.16.8 | Проверка Python-кода | MIT | [GitHub](https://github.com/astral-sh/ruff) |

Важные транзитивные Python-компоненты: NumPy 2.5.3 (BSD-3-Clause, 0BSD, MIT, Zlib, CC0-1.0); Starlette 1.7.0 (BSD-3-Clause); certifi 2026.7.22 (MPL-2.0); python-dateutil 2.9.0.post0 (dual license, детали в metadata/проекте); typing-extensions 4.16.0 (PSF-2.0). `uv.lock` включает 34 package entries с маркерами для альтернатив под разные версии Python; для текущего Python 3.14 используются перечисленные версии.

## JavaScript: runtime и инструменты сборки

| Компонент | Версия | Назначение | Лицензия | Источник |
|---|---:|---|---|---|
| React | 19.1.1 | UI | MIT | [GitHub](https://github.com/facebook/react) |
| React DOM | 19.1.1 | Рендеринг DOM | MIT | [GitHub](https://github.com/facebook/react) |
| Cytoscape.js | 3.32.1 | Графовая визуализация | MIT | [GitHub](https://github.com/cytoscape/cytoscape.js) |
| TypeScript | 5.9.2 | Типизация и сборка | Apache-2.0 | [GitHub](https://github.com/microsoft/TypeScript) |
| Vite | 7.3.6 | Dev server и production build | MIT | [GitHub](https://github.com/vitejs/vite) |
| ESLint | 9.36.0 | Lint | MIT | [GitHub](https://github.com/eslint/eslint) |
| eslint-plugin-react-hooks | 5.2.0 | Правила React Hooks | MIT | [GitHub](https://github.com/facebook/react) |
| typescript-eslint | 8.44.1 | TypeScript lint | MIT | [GitHub](https://github.com/typescript-eslint/typescript-eslint) |
| @vitejs/plugin-react | 5.0.3 | React-интеграция Vite | MIT | [GitHub](https://github.com/vitejs/vite-plugin-react) |
| @types/* | версии в package-lock | TypeScript объявления типов | MIT | [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) |

В `frontend/package-lock.json` зафиксировано 243 npm package entries; у всех есть license field. Сводка metadata: MIT — 205, Apache-2.0 — 14, ISC — 14, BSD-2-Clause — 6, BSD-3-Clause — 2, Python-2.0 — 1, CC-BY-4.0 — 1. CC-BY-4.0 указан для транзитивного `caniuse-lite`; сохраняйте его attribution при распространении соответствующих материалов. Полное дерево и разрешённые версии фиксирует package-lock.

## Образы и инструменты контейнера

`Dockerfile` использует официальные образы Docker Hub, закреплённые digest:

- `node:24.21.0-bookworm-slim`, `sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6`;
- `python:3.14.3-slim-bookworm`, `sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2`.

В runtime-слой ставится `uv==0.12.16` из PyPI. Сами образы включают системные компоненты Debian; отдельный полный SBOM образов здесь не приведён. Docker build и Compose up --wait прошли на локальной среде. Образы закреплены по digest.

## Данные и внешние сервисы

Dataset организаторов: [архив](https://drive.google.com/file/d/1yHdWaSb6gwPAUrqco-KrwR2U_YhzFQFT/view), [README dataset](https://drive.google.com/file/d/1ro-SiY042jv7De0h7tXBDyY8ZKdHz_US/view). Файлы разрешены исключительно для хакатона; отдельная публичная лицензия набора не заявлена. Не включать исходные Parquet в коммиты и не распространять за пределами условий организаторов. Fetch использует публичную ссылку Google Drive без участнического аккаунта, cookie или ключа. Другие внешние API, модели и платные сервисы не используются.


В чистой локальной копии `uv sync --frozen` установил 30 Python packages, `npm ci` — 193 npm packages; `npm audit` сообщил 0 уязвимостей. Для разработки и подготовки решения использовался Codex (Astra, Sol, Luna); это не runtime dependency и для запуска приложения Codex не требуется.
