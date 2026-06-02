FROM python:3.11-slim

WORKDIR /app

# curl is required for the compose healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Copy manifest first so dep install is cached independently of source changes
COPY pyproject.toml .
RUN uv pip install --system \
    fastapi \
    "uvicorn[standard]" \
    langgraph \
    langchain-core \
    langchain-openai \
    sqlalchemy \
    pydantic-settings \
    pyyaml \
    pytest

COPY . .

# Ensure the data directory exists for the SQLite volume mount
RUN mkdir -p /app/data

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
