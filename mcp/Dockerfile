FROM python:3.11-slim

# Usuario no-root para runtime
RUN groupadd --system --gid 1000 mcpuser \
    && useradd --system --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin mcpuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=mcpuser:mcpuser server.py .

USER mcpuser

# Default transport: sse (port 8091). Override con MCP_TRANSPORT=stdio si se
# usa como subprocess en lugar de container.
ENV MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8091

EXPOSE 8091

CMD ["python", "server.py"]
