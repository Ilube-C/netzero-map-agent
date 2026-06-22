#!/usr/bin/env bash
# Optional: start the Anthropic-published read-only Postgres MCP server pointed
# at this project's local PostGIS, so Claude Code can run SQL against it.
#
# The server is read-only by design — its `query` tool runs arbitrary SQL but
# only inside a read-only transaction, so DROP/DELETE are rejected even if the
# model is talked into them.
# (Reference: github.com/modelcontextprotocol/servers/tree/main/src/postgres)
#
# Spawned automatically by Claude Code via .mcp.json. Not meant to be invoked
# directly. DATABASE_URL is read from backend/.env if present, else defaults to
# the local docker-compose database.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$PROJECT_ROOT/backend/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    . "$PROJECT_ROOT/backend/.env"
    set +a
fi

DATABASE_URL="${DATABASE_URL:-postgresql://map:map@localhost:5432/map}"

exec npx -y @modelcontextprotocol/server-postgres "$DATABASE_URL"
