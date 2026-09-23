FROM node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.14.3-slim-bookworm@sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    MONEY_GRAPH_DATA=/app/data \
    MONEY_GRAPH_OUT=/app/out \
    MONEY_GRAPH_STATIC=/app/frontend/dist
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.16
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python && rm -rf /root/.cache
COPY backend/ ./backend/
COPY scripts/fetch_data.py ./scripts/fetch_data.py
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN mkdir -p /app/data /app/out
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health'))['ready']"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
