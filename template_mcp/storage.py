"""Generischer File-Store fuer MCP-Tools.

Stelle dies nach deinem Backend an: Files, S3, Datenbank, externe API, etc.
Hier: simpler File-System-Backend mit Path-Traversal-Schutz unter DATA_PATH.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

# Root-Pfad — Container-intern unter `/data` (mountable von host)
DATA_PATH = Path(os.environ.get("DATA_PATH", "/data")).resolve()


class StorageError(Exception):
    """Fehler bei Storage-Operationen (Pfad ausserhalb, File fehlt, ...)."""


def safe_path(rel: str) -> Path:
    """Resolve `rel` gegen DATA_PATH und stelle sicher dass das Ziel
    INNERHALB DATA_PATH liegt (kein `..`-Escape).
    """
    rel = rel.lstrip("/\\")
    target = (DATA_PATH / rel).resolve()
    try:
        target.relative_to(DATA_PATH)
    except ValueError as e:
        raise StorageError(f"Pfad ausserhalb DATA_PATH: {rel}") from e
    return target


def rel_path(p: Path) -> str:
    """Rel-Pfad ab DATA_PATH, mit Forward-Slashes."""
    return str(p.relative_to(DATA_PATH)).replace("\\", "/")


# ---------- Slug + IDs --------------------------------------------------------

_SLUG_KEEP = re.compile(r"[^a-z0-9\-]+")
SLUG_MAX = 60


def slugify(text: str) -> str:
    """Slug-Regel: kleinbuchstaben, Spaces → `-`, sonst alles raus."""
    s = unicodedata.normalize("NFD", text.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(" ", "-")
    s = _SLUG_KEEP.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def validate_slug(slug: str) -> str | None:
    """Returns Fehlertext wenn ungültig, sonst None."""
    if not slug:
        return "Leerer slug"
    if len(slug) > SLUG_MAX:
        return f"Slug zu lang ({len(slug)} > {SLUG_MAX} Zeichen)"
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        return f"Slug enthaelt unguelt. Zeichen: {slug!r}"
    return None


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- File-Operations ---------------------------------------------------


def read_text(rel: str) -> str:
    """Liest UTF-8 Text. Wirft StorageError wenn fehlt."""
    p = safe_path(rel)
    if not p.is_file():
        raise StorageError(f"Datei nicht gefunden: {rel}")
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def write_text(rel: str, content: str) -> str:
    """Schreibt UTF-8 Text. Erstellt Parent-Ordner wenn noetig.
    Returns rel-Pfad (unveraendert).
    """
    p = safe_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return rel


def delete_file(rel: str) -> None:
    """Loescht eine Datei. Raeumt leere Parent-Folder auf."""
    p = safe_path(rel)
    if not p.is_file():
        raise StorageError(f"Datei nicht gefunden: {rel}")
    p.unlink()
    parent = p.parent
    while parent != DATA_PATH and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def list_dir(rel: str = "") -> list[dict]:
    """Listet Inhalt eines Folders (Files + Subfolders, sortiert)."""
    d = DATA_PATH if rel in ("", "/") else safe_path(rel)
    if not d.is_dir():
        raise StorageError(f"Folder nicht gefunden: {rel}")
    entries = []
    for child in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            entries.append({"kind": "dir", "name": child.name, "path": rel_path(child)})
        else:
            stat = child.stat()
            entries.append({
                "kind": "file", "name": child.name, "path": rel_path(child),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
    return entries


def grep(query: str, scope: str = "", max_results: int = 50) -> list[dict]:
    """Volltext-Regex-Suche (case-insensitive) durch alle Files."""
    flags = re.IGNORECASE
    try:
        pattern = re.compile(query, flags)
    except re.error as e:
        raise StorageError(f"Ungueltiges Regex-Pattern: {e}") from e

    base = DATA_PATH if scope in ("", "/") else safe_path(scope)
    if not base.is_dir():
        raise StorageError(f"Folder nicht gefunden: {scope}")

    hits = []
    for p in base.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if pattern.search(line):
                hits.append({
                    "path": rel_path(p),
                    "line": i,
                    "match": line.strip()[:200],
                })
                if len(hits) >= max_results:
                    return hits
    return hits
