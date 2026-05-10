"""Setup-Script: OAuth-Password setzen.

Fragt das Passwort interaktiv ab (verlaesst nie die Console),
generiert einen bcrypt-Hash und gibt eine Zeile aus, die du in deine
.env einfuegst.

Usage (lokal):
    python scripts/set_oauth_password.py

Usage (im laufenden Container):
    docker exec -it <container-name> python /app/scripts/set_oauth_password.py

WICHTIG: '-it' damit getpass funktioniert (interaktive TTY).

Achtung: docker-compose env_file interpretiert `$` als Variable. Nach dem
Einfuegen des Hashes in .env die `$` doppeln (idempotent):

    sed -i '/^OAUTH_PASSWORD_HASH=/ s|\\$\\+|$$|g' .env
"""

from __future__ import annotations

import getpass
import os
import sys

import bcrypt


def main() -> int:
    print("OAuth — Password setzen")
    print("-" * 40)
    email = os.environ.get("OAUTH_USER_EMAIL", "").strip()
    if not email:
        email = input("Email (OAUTH_USER_EMAIL): ").strip()
        if not email:
            print("FAIL: Email darf nicht leer sein.")
            return 1
    print(f"User: {email}")
    print()

    pw1 = getpass.getpass("Neues Passwort: ")
    if not pw1 or len(pw1) < 8:
        print("FAIL: Passwort muss >= 8 Zeichen sein.")
        return 1
    pw2 = getpass.getpass("Wiederholen: ")
    if pw1 != pw2:
        print("FAIL: Passwoerter stimmen nicht ueberein.")
        return 1

    h = bcrypt.hashpw(pw1.encode("utf-8"), bcrypt.gensalt(rounds=12))
    hash_str = h.decode("ascii")

    print()
    print("OK — fuege diese Zeilen in deine .env ein:")
    print()
    print(f"OAUTH_USER_EMAIL={email}")
    print(f"OAUTH_PASSWORD_HASH={hash_str}")

    # Plus JWT-Secret falls noch nicht da
    if not os.environ.get("OAUTH_JWT_SECRET"):
        import secrets
        jwt_secret = secrets.token_urlsafe(48)
        print(f"OAUTH_JWT_SECRET={jwt_secret}")

    print()
    print("Bei docker-compose: anschliessend `$`-Zeichen im Hash doppeln, dann Container restart:")
    print(r"  sed -i '/^OAUTH_PASSWORD_HASH=/ s|\$\+|$$|g' .env")
    print("  docker compose restart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
