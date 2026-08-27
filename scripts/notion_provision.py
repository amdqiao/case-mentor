#!/usr/bin/env python3
"""
Give an empty Notion database the schema CaseMentor writes to.

Called by setup.sh. The user creates a blank database and shares it with their
integration; everything below is derived from the URL.

Only missing properties are added, and the title property is renamed rather than
replaced, so re-running this on a database that already has rows is safe.

    notion_provision.py <token> <database-url-or-id>

Prints "<data_source_id> <database_id>" on success.
"""

import json
import re
import sys
import urllib.error
import urllib.request

# The schema SKILL.md writes to. The grade properties use an EN DASH (U+2013).
DESIRED: dict[str, dict] = {
    "Date": {"date": {}},
    "Sector": {"rich_text": {}},
    "Case Type": {"rich_text": {}},
    "PDF Link": {"url": {}},
    "A – Analytical": {"select": {"options": [{"name": str(n)} for n in (1, 2, 3, 4)]}},
    "B – Conceptual": {"select": {"options": [{"name": str(n)} for n in (1, 2, 3, 4)]}},
    "C – Quantitative": {"select": {"options": [{"name": str(n)} for n in (1, 2, 3, 4)]}},
    "Spike": {"multi_select": {"options": [{"name": c} for c in ("A", "B", "C")]}},
    "Completion": {"select": {"options": [{"name": "Full"}, {"name": "Partial"}]}},
    "Completed States": {"rich_text": {}},
    "Notes": {"rich_text": {}},
}

TITLE_PROPERTY = "Case Name"


def extract_id(text: str) -> str:
    """
    Accept a full Notion URL, a share link, or a bare id.

    A database URL looks like
      https://www.notion.so/workspace/38d86378d3b94eefb6bcb8e89f9dc494?v=<view-id>
    The view id after `?v=` is also 32 hex, so anything past the query string is
    discarded before matching or the wrong id gets picked up.
    """
    head = text.split("?", 1)[0]
    ids = re.findall(r"[0-9a-fA-F]{32}", head.replace("-", ""))
    if not ids:
        raise SystemExit(
            "Could not find a database id in that input.\n"
            "Open the database as a full page and copy the URL from the address bar."
        )
    return ids[-1]


def api(token: str, method: str, path: str, version: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"https://api.notion.com/v1/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def fail(msg: str, detail: str = "") -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    if detail:
        print(detail.strip()[:400], file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: notion_provision.py <token> <database-url-or-id>")
    token, raw = sys.argv[1], sys.argv[2]
    db_id = extract_id(raw)

    try:
        db = api(token, "GET", f"databases/{db_id}", "2025-09-03")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code in (401, 403):
            fail("Notion refused the token, or the database is not shared with the "
                 "integration.\nOpen the database -> ... -> Connections -> add your "
                 "integration, then rerun.", detail)
        if e.code == 404:
            fail("No database with that id is visible to this integration.\n"
                 "Check the URL, and that the database is shared with the integration.",
                 detail)
        fail(f"Notion returned HTTP {e.code}", detail)

    data_sources = db.get("data_sources") or []
    ds_id = data_sources[0]["id"] if data_sources else ""

    # Read the current schema from the data source when there is one; older workspaces
    # return properties on the database object itself.
    current: dict = db.get("properties") or {}
    if ds_id and not current:
        try:
            current = api(token, "GET", f"data_sources/{ds_id}", "2025-09-03").get("properties", {})
        except urllib.error.HTTPError:
            current = {}

    patch: dict[str, dict] = {name: spec for name, spec in DESIRED.items() if name not in current}

    # Rename whatever the title column is called ("Name" in a fresh database) rather than
    # adding a second one — a database may have exactly one title property.
    title_now = next((n for n, p in current.items() if p.get("type") == "title"), None)
    if title_now and title_now != TITLE_PROPERTY:
        patch[title_now] = {"name": TITLE_PROPERTY}
    elif not title_now and TITLE_PROPERTY not in current:
        patch[TITLE_PROPERTY] = {"title": {}}

    if not patch:
        print(f"{ds_id} {db_id}")
        print("Schema already correct; nothing to change.", file=sys.stderr)
        return

    attempts = []
    if ds_id:
        attempts.append(("data_sources/" + ds_id, "2025-09-03"))
    attempts.append(("databases/" + db_id, "2022-06-28"))

    last = ""
    for path, version in attempts:
        try:
            api(token, "PATCH", path, version, {"properties": patch})
            added = sorted(n for n in patch if n not in current)
            print(f"{ds_id} {db_id}")
            print(f"Added {len(added)} propert{'y' if len(added) == 1 else 'ies'}: "
                  f"{', '.join(added)}", file=sys.stderr)
            return
        except urllib.error.HTTPError as e:
            last = e.read().decode(errors="replace")

    fail("Could not update the database schema.", last)


if __name__ == "__main__":
    main()
