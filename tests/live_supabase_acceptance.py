"""Protected live acceptance; exact-resource manifests survive Molecule pruning."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runner import changed, invoke

PROJECT = "madebyphunky.supabase.project"
AUTH = "madebyphunky.supabase.auth"
MIGRATIONS = "madebyphunky.supabase.migrations"


def request(endpoint, method="GET", body=None):
    headers = {
        "Authorization": "Bearer " + os.environ["SUPABASE_ACCESS_TOKEN"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = Request(
        "https://api.supabase.com" + endpoint,
        headers=headers,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
    )
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        raise RuntimeError(
            f"supabase {method} {endpoint} returned HTTP {error.code}"
        ) from None


def projects():
    rows = request("/v1/projects")
    assert isinstance(rows, list), "Unsupported Project list"
    return rows


def project(manifest, name):
    matches = [
        row
        for row in projects()
        if row.get("name") == name
        and manifest["organization_id"]
        in (row.get("organization_id"), row.get("organization_slug"))
    ]
    if not matches:
        return None
    assert len(matches) == 1, "Ambiguous Project name in Organization"
    return matches[0]


def project_by_ref(ref):
    return request("/v1/projects/" + ref)


def save(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def created_ms(row):
    value = row.get("created_at") or row.get("inserted_at")
    assert value, "Project creation timestamp missing"
    if isinstance(value, (int, float)):
        return int(value if value > 10_000_000_000 else value * 1000)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def capture(path, manifest):
    """Recover exact refs even when a public Role invocation stops after partial progress."""
    for name in manifest["projects"]:
        item = project(manifest, name)
        if item is None:
            continue
        assert item.get("name") == name, "Project identity mismatch"
        assert manifest["organization_id"] in (
            item.get("organization_id"),
            item.get("organization_slug"),
        ), "Project organization mismatch"
        assert (
            created_ms(item) >= manifest["started_ms"] - 1000
        ), "Pre-existing Project; refusing ownership"
        ref = item.get("ref") or item.get("id")
        assert ref and re.fullmatch(r"[a-z]{20}", ref), "Unexpected Project reference"
        assert manifest["projects"][name] in (
            None,
            ref,
        ), "Project reference changed; refusing ownership"
        manifest["projects"][name] = ref
    save(path, manifest)


def public_result(output, key="project"):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", output):
        try:
            value, _ = decoder.raw_decode(output[match.start() :])
            message = value.get("msg") if isinstance(value, dict) else None
            parsed = json.loads(message) if isinstance(message, str) else message
            if isinstance(parsed, dict) and key in parsed:
                return parsed
            if isinstance(value, dict):
                for candidate in value.values():
                    if isinstance(candidate, dict) and key in candidate:
                        return candidate
        except (ValueError, TypeError):
            continue
    raise AssertionError("Public Role result was not returned")


def password():
    value = os.environ["SUPABASE_TEST_PASSWORD"]
    assert value.strip(), "SUPABASE_TEST_PASSWORD must be nonblank"
    return value


def project_vars(manifest, name=None, ref=None):
    values = {
        "SUPABASE_ACCESS_TOKEN": os.environ["SUPABASE_ACCESS_TOKEN"],
        "supabase_organization": manifest["organization"],
        "supabase_project_name": name or manifest["main"],
        "supabase_region": manifest["region"],
        "supabase_project_password": password(),
    }
    if ref:
        values["supabase_project_ref"] = ref
    return values


def run_role(path, manifest, role, values, check=False, expected_changes=None):
    result_key = {
        PROJECT: "supabase_project_result",
        AUTH: "supabase_auth_result",
        MIGRATIONS: "supabase_migrations_result",
    }[role]
    try:
        result = invoke(
            values,
            role=role,
            check=check,
            timeout=1200,
            tasks_after=[
                {
                    "name": "Return public acceptance result",
                    "ansible.builtin.debug": {
                        "msg": "{{ " + result_key + " | to_json }}"
                    },
                }
            ],
        )
        for secret in (
            os.environ["SUPABASE_ACCESS_TOKEN"],
            password(),
            os.environ.get("SUPABASE_TEST_SMTP_PASS", ""),
        ):
            if secret:
                assert secret not in result.stdout, "Credential appeared in output"
        assert result.returncode == 0, result.stdout
        if expected_changes is not None:
            assert changed(result) == expected_changes, result.stdout
        return public_result(result.stdout, "project")
    finally:
        capture(path, manifest)


def prepare(path):
    if path.exists():
        raise RuntimeError(
            "Retained live manifest exists; clean it up before starting another run"
        )
    required = (
        "SUPABASE_ACCESS_TOKEN",
        "SUPABASE_TEST_ORGANIZATION",
        "SUPABASE_TEST_REGION",
        "SUPABASE_TEST_PASSWORD",
    )
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError(
            "Set all protected live-test credentials and organization/region variables"
        )
    organization = os.environ["SUPABASE_TEST_ORGANIZATION"]
    orgs = request("/v1/organizations")
    assert isinstance(orgs, list), "Unsupported organization list"
    matches = [
        row
        for row in orgs
        if organization in (row.get("id"), row.get("slug"), row.get("name"))
    ]
    assert len(matches) == 1, "Explicit organization must resolve uniquely"
    org = matches[0]
    prefix = "ansible-live-" + uuid.uuid4().hex[:12]
    main, sentinel = (prefix + "-" + suffix for suffix in ("main", "sentinel"))
    manifest = {
        "organization": organization,
        "organization_id": org.get("id") or org.get("slug"),
        "organization_slug": org.get("slug"),
        "region": os.environ["SUPABASE_TEST_REGION"],
        "main": main,
        "sentinel": sentinel,
        "projects": {main: None, sentinel: None},
        "fixture_dir": None,
        "started_ms": int(time.time() * 1000),
        "commit": os.environ.get("GITHUB_SHA")
        or os.environ.get("SUPABASE_TEST_COMMIT")
        or "",
        "cli_version": None,
    }
    assert all(
        project(manifest, name) is None for name in manifest["projects"]
    ), "Allocated Project already exists"
    save(path, manifest)
    run_role(path, manifest, PROJECT, project_vars(manifest, sentinel))


def fixture_dir(manifest):
    root = Path(manifest["fixture_dir"] or "")
    if not root.exists():
        root = Path(".cache/supabase-live/fixtures") / manifest["main"]
        root.mkdir(parents=True, exist_ok=True)
        (root / "supabase" / "migrations").mkdir(parents=True)
        (root / "supabase" / "migrations" / "20261102190000_widgets.sql").write_text(
            "create table public.widgets (id int primary key);\n"
        )
        (root / "supabase" / "config.toml").write_text(
            '[auth]\nsite_url = "https://acceptance.example.test"\n'
            'additional_redirect_urls = ["https://acceptance.example.test/callback"]\n'
        )
        smtp = os.environ.get("SUPABASE_TEST_SMTP_PASS")
        if smtp:
            auth = root / "auth-secret.toml"
            auth.write_text(
                "[auth.email.smtp]\nenabled = true\n"
                'host = "smtp.example.test"\n'
                "port = 587\n"
                'user = "acceptance"\n'
                'pass = "' + smtp.replace("\\", "\\\\").replace('"', '\\"') + '"\n'
                'admin_email = "acceptance@example.test"\n'
                'sender_name = "Acceptance"\n'
            )
            manifest["auth_secret_config"] = str(auth)
        manifest["fixture_dir"] = str(root)
        manifest["auth_config"] = str(root / "supabase" / "config.toml")
    return Path(manifest["fixture_dir"])


def sql(manifest, ref, query):
    return request(
        "/v1/projects/" + ref + "/database/query",
        "POST",
        {"query": query},
    )


def verify(path, manifest):
    capture(path, manifest)
    sentinel_before = project(manifest, manifest["sentinel"])
    assert sentinel_before is not None
    fixture_dir(manifest)
    save(path, manifest)
    main = project_vars(manifest)
    created = run_role(path, manifest, PROJECT, main, expected_changes=0)
    ref = created["project"]["ref"]
    assert ref == manifest["projects"][manifest["main"]]
    assert created["project"].get("status") in (None, "ACTIVE_HEALTHY")
    for key in ("initial_password", "db_password", "password"):
        assert key not in created
        assert key not in created.get("project", {})
    adopted = run_role(
        path,
        manifest,
        PROJECT,
        project_vars(manifest, ref=ref),
        expected_changes=0,
    )
    assert adopted["project"]["ref"] == ref
    rotated = dict(main, supabase_project_password="different-" + password())
    run_role(path, manifest, PROJECT, rotated, expected_changes=0)
    auth_config = {
        "SUPABASE_ACCESS_TOKEN": os.environ["SUPABASE_ACCESS_TOKEN"],
        "supabase_project_ref": ref,
        "supabase_auth_config": manifest["auth_config"],
    }
    run_role(path, manifest, AUTH, auth_config)
    run_role(path, manifest, AUTH, auth_config, expected_changes=0)
    if manifest.get("auth_secret_config"):
        secret_vars = dict(
            auth_config, supabase_auth_config=manifest["auth_secret_config"]
        )
        run_role(path, manifest, AUTH, secret_vars)
        run_role(path, manifest, AUTH, secret_vars, expected_changes=0)
    migration_vars = {
        "SUPABASE_ACCESS_TOKEN": os.environ["SUPABASE_ACCESS_TOKEN"],
        "SUPABASE_DB_PASSWORD": password(),
        "supabase_project_ref": ref,
        "supabase_workdir": manifest["fixture_dir"],
    }
    run_role(path, manifest, MIGRATIONS, migration_vars)
    try:
        rows = sql(manifest, ref, "select to_regclass('public.widgets') as relation")
        assert rows and "widgets" in json.dumps(rows), rows
    except RuntimeError as error:
        if "HTTP 404" not in str(error) and "HTTP 403" not in str(error):
            raise
    run_role(path, manifest, MIGRATIONS, migration_vars, expected_changes=0)
    conflict = Path(manifest["fixture_dir"]) / "supabase/migrations"
    (conflict / "20261101190000_conflict.sql").write_text(
        "create table public.conflict (id int);\n"
    )
    failed = invoke(migration_vars, role=MIGRATIONS, timeout=1200)
    assert failed.returncode != 0
    capture(path, manifest)
    (conflict / "20261101190000_conflict.sql").unlink()
    before = project(manifest, manifest["main"])
    run_role(path, manifest, PROJECT, main, check=True)
    assert project(manifest, manifest["main"]) == before, "Check mode mutated Project"
    assert (
        project(manifest, manifest["sentinel"]) == sentinel_before
    ), "Unrelated Project changed"
    version = subprocess.run(
        ["npx", "--yes", "supabase@latest", "--version"],
        check=False,
        text=True,
        capture_output=True,
        timeout=120,
    )
    match = re.search(r"(\d+\.\d+\.\d+)", version.stdout + version.stderr)
    if match:
        manifest["cli_version"] = match.group(1)
        save(path, manifest)
    print(
        "Supabase create/adopt/idempotency, Auth, migrations, password non-rotation, "
        "check mode, and sentinel preservation passed "
        f"(commit={manifest.get('commit') or 'local'}, "
        f"cli={manifest.get('cli_version') or 'unresolved'})"
    )


def cleanup(path, manifest):
    capture(path, manifest)
    failures = []
    for name, expected_ref in manifest["projects"].items():
        try:
            current = project(manifest, name)
            if current is None:
                continue
            ref = current.get("ref") or current.get("id")
            assert (
                expected_ref and ref == expected_ref
            ), "Project reference changed; refusing deletion"
            request("/v1/projects/" + expected_ref, "DELETE")
            assert project(manifest, name) is None, "Project deletion not confirmed"
        except Exception as error:
            failures.append(str(error))
    fixture = manifest.get("fixture_dir")
    if fixture:
        try:
            root = Path(fixture)
            if root.exists():
                for child in sorted(root.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                root.rmdir()
        except Exception as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError(
            "Cleanup incomplete; retain manifest and retry: " + "; ".join(failures)
        )
    path.unlink()


def main():
    action, path = sys.argv[1], Path(sys.argv[2])
    if action == "prepare":
        prepare(path)
    elif action == "cleanup" and not path.exists():
        return
    else:
        manifest = json.loads(path.read_text())
        if action == "converge":
            fixture_dir(manifest)
            save(path, manifest)
            run_role(path, manifest, PROJECT, project_vars(manifest))
        elif action == "verify":
            verify(path, manifest)
        elif action == "cleanup":
            cleanup(path, manifest)
        else:
            raise RuntimeError("Unknown acceptance action")


if __name__ == "__main__":
    main()
