FROM python:3.12.11-slim
# TODO(digest): resolve and pin the registry digest in the connected build environment.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .

RUN addgroup --system gamedai && \
    adduser --system --ingroup gamedai gamedai && \
    pip install --no-cache-dir .

USER gamedai

EXPOSE 8080

CMD ["gamedai-nfl-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
