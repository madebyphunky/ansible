#!/usr/bin/env python3
"""Stateful CLI double matching official Supabase v3 JSON output contracts."""

import json
import os
from pathlib import Path
import sys
import tomllib

path = Path(os.environ["ANSIBLE_SUPABASE_CONTRACT_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
assert args[0] == "--yes"
package = args[1]
args = args[2:]
assert package.startswith("supabase@")
assert os.environ["SUPABASE_ACCESS_TOKEN"] == "dummy-explicit-token"
assert "SUPABASE_AUTH_SITE_URL" not in os.environ
assert Path(os.environ["SUPABASE_HOME"]).parent.resolve() == Path.cwd()
assert not Path("supabase/.temp/project-ref").exists()
operation = " ".join(args[:2])
call = {"operation": operation, "version": package, "args": list(args)}
if "--db-password" in args:
    index = args.index("--db-password") + 1
    state["password"] = args[index]
    call["args"][index] = "<redacted>"
state.setdefault("calls", []).append(call)


def finish(data=None, code=0):
    path.write_text(json.dumps(state))
    if data is not None:
        print(json.dumps(data))
    sys.exit(code)


if state.get("fail") == operation:
    print(
        "provider failure may echo secret: "
        + state.get("password", "dummy-explicit-token"),
        file=sys.stderr,
    )
    finish(code=1)
if operation == "orgs list":
    finish([{"id": "org-id", "slug": "my-org", "name": "Organization"}])
if operation == "projects list":
    finish(state.get("projects", []))
if operation == "projects create":
    assert args[args.index("--org-id") + 1] == "my-org"
    assert state["password"]
    row = {
        "id": "abcdefghijabcdefghij",
        "ref": "abcdefghijabcdefghij",
        "name": args[2],
        "organization_id": "org-id",
        "organization_slug": "my-org",
        "region": args[args.index("--region") + 1],
        "status": state.get("status", "ACTIVE_HEALTHY"),
    }
    state.setdefault("projects", []).append(row)
    if state.get("fail_after_create"):
        finish(code=1)
    finish(row)

assert "--remote=abcdefghijabcdefghij" in args
if operation.startswith("config "):
    config = tomllib.loads(Path("supabase/config.toml").read_text())
    assert set(config) == {"auth"}, "non-Auth config escaped role ownership"
    state["staged_auth"] = config
    staged = []
    for staged_path in sorted(Path("supabase").rglob("*")):
        if staged_path.is_file() and staged_path.as_posix() != "supabase/config.toml":
            staged.append(staged_path.as_posix())
    state["staged_files"] = staged

    def flatten(value, prefix=()):
        fields = {}
        for key, item in value.items():
            if isinstance(item, dict):
                fields.update(flatten(item, prefix + (key,)))
            else:
                fields[prefix + (key,)] = item
        return fields

    local = flatten(config)
    remote = flatten({"auth": state.get("auth", {})})
    secret_paths = {
        key
        for key in local
        if key[-1] in ("pass", "secret", "client_secret", "password")
    }
    changes = []
    for key in local.keys() | remote.keys():
        if key[-1] in ("pass", "secret", "client_secret", "password"):
            continue
        if key not in local:
            kind = "remote_only"
        elif key not in remote:
            kind = "local_only"
        elif local[key] != remote[key]:
            kind = "update"
        else:
            continue
        changes.append(
            {
                "path": key,
                "class": kind,
                "declared": key in local,
                "local": local.get(key),
                "remote": remote.get(key),
            }
        )
    if operation == "config diff":
        assert "--output-format" in args and "-o" not in args
        counts = {
            key: sum(item["class"] == key for item in changes)
            for key in ("update", "remote_only", "local_only")
        }
        finish(
            {
                "schema_version": 1,
                "target": {"project_ref": "abcdefghijabcdefghij"},
                "counts": counts | {"total": len(changes)},
                "changes": changes,
                "scope": {
                    "present": ["auth"],
                    "missing": state.get("missing_scope", []),
                },
                "masked": list(secret_paths),
                "unmanaged": [],
            },
            code=2 if changes else 0,
        )
    assert operation == "config push"

    def merge(destination, supplied):
        for key, value in supplied.items():
            if isinstance(value, dict):
                merge(destination.setdefault(key, {}), value)
            else:
                destination[key] = value

    actual_change = any(remote.get(key) != value for key, value in local.items())
    sent = [key for key in secret_paths if remote.get(key) != local[key]]
    unchanged = [key for key in secret_paths if remote.get(key) == local[key]]
    merge(state.setdefault("auth", {}), config["auth"])
    finish(
        {
            "schema_version": 1,
            "project_ref": "abcdefghijabcdefghij",
            "services": [
                {
                    "service": "auth",
                    "status": state.get(
                        "push_status", "updated" if actual_change else "up_to_date"
                    ),
                }
            ],
            "unsupported": [],
            "unencodable": [],
            "secrets": {"sent": sent, "unchanged": unchanged},
            "scope": {"present": ["auth"], "missing": []},
        }
    )
if operation == "db push":
    assert os.environ["SUPABASE_DB_PASSWORD"] in (
        "dummy-db-password",
        state.get("password"),
    )
    assert "--skip-vault" in args
    assert not any(
        arg in args
        for arg in ("--include-all", "--include-seed", "--include-roles", "--password")
    )
    assert set(Path("supabase").iterdir()) == {
        Path("supabase/config.toml"),
        Path("supabase/migrations"),
    }
    files = sorted(item.name for item in Path("supabase/migrations").glob("*.sql"))
    applied = state.get("applied", [])
    if state.get("history_conflict"):
        finish(code=1)
    pending = [name for name in files if name not in applied]
    dry_run = "--dry-run" in args
    if not dry_run:
        state["applied"] = applied + pending
    finish(
        {
            "upToDate": not pending,
            "dryRun": dry_run,
            "migrations": pending,
            "seeds": [],
            "roles": [],
            "target": {"kind": "linked", "project_ref": "abcdefghijabcdefghij"},
            "message": "Finished supabase db push.",
        }
    )
finish(code=1)
