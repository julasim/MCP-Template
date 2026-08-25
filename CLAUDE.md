<!--
ANWEISUNG AN CLAUDE: Diese Datei zuerst lesen, um den Ordner zu verstehen.
Vor dem Beenden der Arbeit hier: Status/Änderungslog pflegen.
-->

# mcp-template — Skelett für neue MCP-Server

Zuletzt aktualisiert: 2026-07-23

## Worum geht's

**Vorlage, kein Produkt.** Production-ready Skelett für einen MCP-Server, aus dem
neue Server abgeleitet werden. Wer hier arbeitet, verbessert die *Vorlage* — laufende
Server sind eigene Projekte und erben Änderungen nicht automatisch.

Remote: `github.com/julasim/MCP-Template`.

## Was drin ist

Streamable HTTP via FastMCP · **Dual-Auth** (Bearer *und* OAuth 2.1 parallel) ·
OAuth-Flows (Auth-Code + PKCE/S256, DCR nach RFC 7591, Refresh-Rotation, Revoke) ·
Discovery (RFC 9728 + RFC 8414) · Audit-Log (JSONL, sensitive Werte maskiert) ·
Token-Bucket-Rate-Limit pro IP · tar.gz-Snapshots vor destruktiven Operationen ·
Pre-Write-Validators · Boot-Security-Checks · Path-Traversal-Schutz ·
`/health` ohne Auth · Docker (slim, non-root).

Spec-Stand: MCP 2025-06-18, OAuth 2.1.

## Ableiten eines neuen Servers

1. Repo kopieren/klonen, `template_mcp/` umbenennen, `pyproject.toml` anpassen.
2. Die **5 Beispiel-Tools** (`search`, `read_file`, `list_files`, `create_note`,
   `edit_file_replace`) durch die eigenen Domain-Tools ersetzen — sie sind
   Demonstration der Annotations (`readOnlyHint`/`destructiveHint`/
   `idempotentHint`/`openWorldHint`), nicht Funktionsumfang.
3. `.env` aus `.env.example`; Secrets nie ins Image.
4. Deployment nach `~/.claude/SERVER-PLAYBOOK.md` (Edge-Proxy, Zwei-Netzwerke-Modell).

## Status

Stabil und unverändert seit 2026-05-10 (letzter Commit: Template-Audit-Fixes, drei
Ship-Blocker — Any-Import, Lifespan, `/mcp/`+`/mcp`). Wird nur angefasst, wenn ein
abgeleiteter Server einen Mangel in der Vorlage aufdeckt.

## Wichtig

- **Bewusst mit OAuth.** Nicht jeder abgeleitete Server braucht das:
  `apps/rag-os-app-lokal` hat OAuth/TOTP bewusst wieder **entfernt** und fährt
  Bearer-only read-only. Beim Ableiten also aktiv entscheiden, nicht nur erben.
- Die Nummerierung der RFCs im README ist Teil der Compliance-Zusage — beim
  Ändern von Auth-Code prüfen, ob sie noch stimmt.
