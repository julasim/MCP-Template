# template-mcp

Production-ready Skelett fuer einen MCP-Server. Enthaelt alles, was im
KI-OS-Vault-MCP gehaertet wurde: Dual-Auth (Bearer + OAuth 2.1), Audit-Log,
Rate-Limiting, Backup-Snapshots, Pre-Write-Validators, Boot-Security-Checks,
Spec-Compliance (MCP 2025-06-18, OAuth 2.1, RFC 7591/7636/8414/9728).

Stelle die 5 Beispiel-Tools (`search`, `read_file`, `list_files`,
`create_note`, `edit_file_replace`) nach mit deinen Domain-Tools.

## Was du bekommst

| Bereich | Implementiert |
|---|---|
| MCP-Transport | Streamable HTTP via FastMCP |
| Tool-Annotations | `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint` |
| Auth | Bearer-Token **und** OAuth 2.1 parallel via Dual-Auth-Middleware |
| OAuth-Flows | Auth-Code + PKCE (S256), DCR (RFC 7591), Refresh-Rotation, Revoke |
| Discovery | `.well-known/oauth-protected-resource` (RFC 9728) + `oauth-authorization-server` (RFC 8414) |
| Login-UI | Custom HTML-Form auf `/oauth/authorize` |
| Audit-Log | JSONL, Tool-Calls + Auth-Events, sensitive Werte maskiert |
| Rate-Limit | Token-Bucket pro Client-IP (default 60/min, env-konfigurierbar) |
| Snapshots | tar.gz vor jeder destruktiven Operation |
| Validators | Pre-Write-Checks fuer alle Inputs |
| Boot-Checks | Warnt bei schwachen Secrets, nicht-schreibbarem Audit-Dir |
| Async-Sicherheit | bcrypt + SQLite via `asyncio.to_thread` (kein Event-Loop-Deadlock) |
| Storage | File-System unter `DATA_PATH` mit Path-Traversal-Schutz |
| Health | `/health` ohne Auth, fuer Caddy/Compose Healthcheck |
| Docker | Multi-Stage `Dockerfile`, Non-Root, Healthcheck, slim Base |

## Schnellstart (lokal)

```bash
# 1) Repo klonen
git clone https://github.com/julasim/MCP-Template.git my-mcp
cd my-mcp

# 2) ENV vorbereiten
cp .env.example .env

# 3) Bearer-Token generieren (mind. 32 Zeichen)
python -c "import secrets; print('MCP_TOKEN=' + secrets.token_urlsafe(48))" >> .env

# 4) (Optional) OAuth aktivieren
python -c "import secrets; print('OAUTH_JWT_SECRET=' + secrets.token_urlsafe(48))" >> .env
python scripts/set_oauth_password.py    # erzeugt OAUTH_PASSWORD_HASH

# 5) Compose starten
cp docker-compose.example.yml docker-compose.yml
docker compose up -d --build

# 6) Smoke-Test
docker exec template-mcp python scripts/smoke_test.py http://localhost:5002
```

## Production-Deployment (hinter Caddy)

Im Container nur `127.0.0.1:5002` bind, TLS via Reverse-Proxy. Beispiel-Caddyfile:

```caddy
mcp.example.com {
    # claude.ai schickt /mcp ohne Slash; Mount("/mcp") in Starlette gibt 404
    @mcp_noslash path /mcp
    rewrite @mcp_noslash /mcp/

    # CSP-Override fuer das Login-HTML
    @oauth_html path /oauth/authorize
    header @oauth_html Content-Security-Policy "default-src 'self'; style-src 'unsafe-inline'"

    reverse_proxy 127.0.0.1:5002
}
```

Anschliessend in `.env` setzen:

```
OAUTH_ISSUER=https://mcp.example.com
OAUTH_RESOURCE=https://mcp.example.com/mcp/
MCP_ALLOWED_ORIGINS=https://claude.ai,https://chat.openai.com
```

## Auth — wer nutzt was?

| Client | Empfohlenes Verfahren |
|---|---|
| Eigener Bot, CLI-Scripts | Bearer-Token (`MCP_TOKEN`) |
| `claude` CLI | Bearer-Token |
| claude.ai Web-Connector | OAuth 2.1 (PKCE + DCR) |
| ChatGPT / Cursor | OAuth 2.1 |
| Custom-App mit User-Login | OAuth 2.1 |

Beide Verfahren laufen parallel via `DualAuthMiddleware` — der Server probiert
JWT zuerst, faellt zurueck auf statisches Bearer.

## Eigene Tools hinzufuegen

In `template_mcp/server.py`:

```python
@mcp.tool(
    name="my_tool",
    description="Was es macht (1 Satz, fuer Tool-Listings).",
    annotations={
        "title": "My Tool",
        "readOnlyHint": False,        # True wenn nur liest
        "destructiveHint": True,      # True wenn loescht/ueberschreibt
        "idempotentHint": False,      # True wenn doppelter Call dasselbe Ergebnis hat
        "openWorldHint": False,       # True wenn externe APIs angesprochen werden
    },
)
@audit.time_call
def my_tool(arg1: str, arg2: int = 0) -> dict:
    # 1) Validierung (return _err(...) wenn ungueltig)
    err = validators.validate_title(arg1)
    if err:
        return _err(err)

    # 2) Snapshot vor destruktiver Aenderung
    if is_destructive:
        snapshot.snapshot_path(path, content_before, op="my_tool")

    # 3) Geschaeftslogik
    result = do_something(arg1, arg2)

    # 4) Strukturiertes Ergebnis
    return _ok(result=result)
```

Annotations sind ab MCP 2025-06-18 Spec-Pflicht. Vergiss sie nicht.

## Datei-Layout

```
template_mcp/
├── __init__.py            Version
├── server.py              FastMCP + Middleware-Stack + 5 Beispiel-Tools
├── storage.py             File-System-Backend (DATA_PATH, safe_path, slugify, grep)
├── validators.py          Pre-Write-Checks
├── oauth.py               OAuth 2.1 Core (JWT, PKCE, DCR, Refresh-Rotation)
├── oauth_routes.py        Discovery + Authorize + Token + Revoke + Login-HTML
├── audit.py               JSONL Audit-Log mit time_call Decorator
├── ratelimit.py           Token-Bucket Middleware
└── snapshot.py            tar.gz Backups vor destruktiven Ops

scripts/
├── set_oauth_password.py  bcrypt-Hash erzeugen + .env updaten
├── rotate_token.py        MCP_TOKEN in .env neu generieren
└── smoke_test.py          End-to-End Health + Auth-Check

Dockerfile                 Slim Base, Non-Root, Healthcheck
docker-compose.example.yml Standalone-Setup
.env.example               Alle Env-Vars dokumentiert
pyproject.toml             Dependencies mit Major-Bounds
```

## Wichtige Lessons Learned

1. **`$$`-Escape in docker-compose env_file**: bcrypt-Hashes haben `$`-Zeichen
   die docker-compose als Variable interpretiert. Idiom (idempotent):
   ```bash
   sed -i '/^OAUTH_PASSWORD_HASH=/ s|\$\+|$$|g' .env
   ```

2. **Caddy `rewrite` statt `redir` fuer `/mcp` ohne Slash**: claude.ai sendet
   `/mcp` ohne Trailing-Slash, Starlettes `Mount("/mcp")` gibt aber 404.
   `rewrite` ist transparent (kein 307 → claude.ai folgt Redirects nicht
   sauber bei POST mit Body).

3. **bcrypt + SQLite muessen async**: in async-Middleware blockiert sync-I/O
   den Event-Loop unter Last. `asyncio.to_thread(...)` ist Pflicht — siehe
   `*_async()`-Wrapper in `oauth.py`.

4. **TOCTOU bei File-Creation vermeiden**: `os.O_EXCL` statt
   `if not exists(): create()`. Siehe `vault.py`-Pattern in der KI-OS-MCP
   `create_daily_skeleton`.

5. **Multi-Marker-Bug bei `text.split()`**: `text.split(MARKER)[0]` haut bei
   doppelten Markern Daten weg. Loesung: `split(MARKER, 1)[0]` und
   `rsplit(MARKER, 1)[1]`.

## Spec-Compliance

- MCP 2025-06-18 (Tool-Annotations, `isError`, Streamable HTTP)
- OAuth 2.1 (Auth-Code + PKCE pflicht, kein Implicit-Flow, kein password-grant)
- RFC 6749 (OAuth 2.0 Framework)
- RFC 7591 (Dynamic Client Registration)
- RFC 7636 (PKCE — S256 only)
- RFC 8414 (Authorization Server Metadata)
- RFC 9728 (Protected Resource Metadata)
- RFC 6819 §5.2.2.3 (Refresh-Token Rotation + Theft-Detection)

## Lizenz

MIT — copy/paste/modify wie du willst.
