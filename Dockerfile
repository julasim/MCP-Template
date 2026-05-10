# Production-Image fuer template-mcp
# Base-Image bewusst slim (kleinerer Attack-Surface, schnellerer Pull).
FROM python:3.12-slim

# System-Deps: nur was bcrypt + Build-Tools brauchen
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install in zwei Steps fuer Layer-Caching
COPY pyproject.toml ./
COPY template_mcp/ ./template_mcp/
RUN pip install --no-cache-dir -e .

# Optionale Scripts (set_oauth_password, rotate_token, smoke_test)
COPY scripts/ ./scripts/

# Default-Mountpoints — werden von docker-compose volume-mounted
RUN mkdir -p /data /var/log/mcp /var/lib/mcp-oauth /snapshots

# Non-root user
RUN useradd -u 1000 -m mcp && \
    chown -R mcp:mcp /app /data /var/log/mcp /var/lib/mcp-oauth /snapshots
USER mcp

EXPOSE 5002

# Healthcheck — Caddy + Compose nutzen das
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5002/health || exit 1

CMD ["python", "-m", "template_mcp.server"]
