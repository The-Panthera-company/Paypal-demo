# Build from the REPO ROOT, not from agents/:
#   docker build -f agents/Dockerfile -t giving-agents .
# The MCP server lives outside agents/, so the context must include it.
# Render: runtime: docker, dockerContext: ., dockerfilePath: ./agents/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Paths below are relative to the repo root build context.
COPY agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/app ./app
COPY mcp-server/server.py /mcp-server/server.py

ENV MCP_SERVER_PATH=/mcp-server/server.py

# Render injects $PORT. Fall back to 8100 so `docker run -p 8100:8100` also works.
ENV PORT=8100
EXPOSE 8100

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
