"""Smoke-Test fuer template-mcp.

Prueft dass der Server live ist, Health-Endpoint antwortet,
unauthorisiert geblockt wird, und ein Bearer-Token akzeptiert wird.

Usage:
    python scripts/smoke_test.py [BASE_URL] [BEARER_TOKEN]

Defaults: BASE_URL=http://localhost:5002, BEARER_TOKEN aus env MCP_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except urllib.error.URLError as e:
        return 0, str(e)


def _post(url: str, body: bytes, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except urllib.error.URLError as e:
        return 0, str(e)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MCP_BASE_URL", "http://localhost:5002")).rstrip("/")
    token = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("MCP_TOKEN", "").strip()

    failures = 0

    # 1) Health (kein Auth)
    print(f"[1/4] GET {base}/health ... ", end="")
    code, body = _get(f"{base}/health")
    if code == 200 and "status" in body:
        print("OK")
    else:
        print(f"FAIL (code={code}, body={body[:200]})")
        failures += 1

    # 2) MCP ohne Auth → 401
    print(f"[2/4] GET {base}/mcp/ (no auth) ... ", end="")
    code, body = _get(f"{base}/mcp/")
    if code == 401:
        print("OK (401)")
    else:
        print(f"FAIL (expected 401, got {code})")
        failures += 1

    # 3) Discovery: oauth-protected-resource
    print(f"[3/4] GET {base}/.well-known/oauth-protected-resource ... ", end="")
    code, body = _get(f"{base}/.well-known/oauth-protected-resource")
    if code == 200:
        try:
            j = json.loads(body)
            if "resource" in j and "authorization_servers" in j:
                print("OK")
            else:
                print(f"FAIL (missing keys: {list(j)})")
                failures += 1
        except json.JSONDecodeError:
            print(f"FAIL (invalid JSON: {body[:200]})")
            failures += 1
    else:
        print(f"FAIL (code={code})")
        failures += 1

    # 4) MCP mit Bearer (wenn Token gesetzt) — initialize-Request
    if token:
        print(f"[4/4] POST {base}/mcp/ initialize (Bearer) ... ", end="")
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "capabilities": {}, "clientInfo": {"name": "smoke-test", "version": "1"}}
        }).encode("utf-8")
        code, body = _post(
            f"{base}/mcp/", payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}",
            },
        )
        if code in (200, 202):
            print(f"OK ({code})")
        else:
            print(f"FAIL (code={code}, body={body[:200]})")
            failures += 1
    else:
        print("[4/4] (skipped — kein MCP_TOKEN gesetzt)")

    if failures:
        print(f"\n{failures} Test(s) FAILED")
        return 1
    print("\nAlle Tests OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
