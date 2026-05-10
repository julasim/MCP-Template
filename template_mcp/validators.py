"""Pre-Write-Validators fuer Tool-Inputs.

MCP-Best-Practice: Validators laufen VOR jedem Write/Edit/Delete und
geben strukturierte Fehlermeldungen zurueck (statt nackter Exceptions).

Dies sind Beispiel-Validators fuer das Skelett. Stelle sie nach deinen
Domain-Regeln nach:
  - Length-Limits
  - Slug-Format
  - Forbidden Patterns
  - Existence-Checks (mit storage.safe_path)

Konvention: jeder Validator returned `None` wenn OK, sonst einen
human-lesbaren Error-String, der direkt an den Client zurueckgeht.
"""

from __future__ import annotations

import re

from . import storage

# Maximum-Limits — passe an dein Domain-Modell an
TITLE_MAX = 200
BODY_MAX = 100_000     # 100 KB Text
QUERY_MAX = 500


def validate_title(title: str | None) -> str | None:
    """Validiert einen Titel. Optional in vielen Tools."""
    if title is None:
        return None
    if not isinstance(title, str):
        return "title muss ein String sein"
    title = title.strip()
    if not title:
        return "title darf nicht leer sein"
    if len(title) > TITLE_MAX:
        return f"title zu lang ({len(title)} > {TITLE_MAX} Zeichen)"
    if "\n" in title or "\r" in title:
        return "title darf keine Zeilenumbrueche enthalten"
    return None


def validate_body(body: str | None, *, required: bool = False) -> str | None:
    """Validiert einen Body-Text. Erlaubt Markdown, blockt nichts inhaltlich."""
    if body is None or body == "":
        if required:
            return "body ist erforderlich"
        return None
    if not isinstance(body, str):
        return "body muss ein String sein"
    if len(body) > BODY_MAX:
        return f"body zu gross ({len(body)} > {BODY_MAX} Zeichen)"
    return None


def validate_query(query: str | None) -> str | None:
    """Validiert einen Suchbegriff (z.B. fuer grep)."""
    if not query or not isinstance(query, str):
        return "query ist erforderlich"
    query = query.strip()
    if not query:
        return "query darf nicht leer sein"
    if len(query) > QUERY_MAX:
        return f"query zu lang ({len(query)} > {QUERY_MAX} Zeichen)"
    # ReDoS-Schutz: blocke katastrophales Backtracking
    if re.search(r"(\(.*\)\+|\(.*\*\)\*)", query):
        return "query enthaelt potentiell unsafe Regex-Pattern"
    return None


def validate_rel_path(rel: str | None, *, must_exist: bool = False) -> str | None:
    """Validiert einen relativen Pfad gegen DATA_PATH."""
    if not rel or not isinstance(rel, str):
        return "Pfad ist erforderlich"
    rel = rel.strip()
    if not rel:
        return "Pfad darf nicht leer sein"
    try:
        p = storage.safe_path(rel)
    except storage.StorageError as e:
        return str(e)
    if must_exist and not p.exists():
        return f"Pfad existiert nicht: {rel}"
    return None


def validate_slug_input(slug: str | None) -> str | None:
    """Wrap storage.validate_slug fuer einheitliche Fehler-Schnittstelle."""
    if not slug:
        return "slug ist erforderlich"
    return storage.validate_slug(slug)
