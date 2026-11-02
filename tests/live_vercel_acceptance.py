"""Protected live acceptance; exact-resource manifests survive Molecule pruning."""

import base64
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from runner import changed, invoke

ROLE = "madebyphunky.vercel.project"


def request(provider, endpoint, method="GET", body=None):
    token_name = "VERCEL_TOKEN" if provider == "vercel" else "GH_TOKEN"
    base = (
        "https://api.vercel.com" if provider == "vercel" else "https://api.github.com"
    )
    headers = {
        "Authorization": "Bearer " + os.environ[token_name],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = Request(
        base + endpoint,
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
        # Provider response bodies may contain sensitive content. Report status only.
        raise RuntimeError(
            f"{provider} {method} {endpoint} returned HTTP {error.code}"
        ) from None


def scoped(manifest, path):
    if manifest["scope_type"] == "team":
        return (
            path
            + ("&" if "?" in path else "?")
            + urlencode({"teamId": manifest["scope_id"]})
        )
    return path


def project(manifest, name):
    return request("vercel", scoped(manifest, "/v9/projects/" + quote(name, safe="")))


def repository(manifest):
    return request(
        "github", "/repos/" + manifest["owner"] + "/" + manifest["repository_name"]
    )


def save(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def capture(path, manifest):
    """Recover exact IDs even when a public Role invocation stops after partial progress."""
    for name in manifest["projects"]:
        item = project(manifest, name)
        if item is not None:
            assert item.get("name") == name, "Project identity mismatch"
            assert (
                item.get("accountId") == manifest["scope_id"]
            ), "Project account mismatch"
            assert (
                item.get("createdAt", 0) >= manifest["started_ms"]
            ), "Pre-existing Project; refusing ownership"
            assert manifest["projects"][name] in (
                None,
                item["id"],
            ), "Project ID changed; refusing ownership"
            manifest["projects"][name] = item["id"]
    item = repository(manifest)
    if item is not None:
        created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        assert (
            created.timestamp() >= manifest["started_ms"] / 1000 - 1
        ), "Pre-existing repository; refusing ownership"
        assert (
            item["full_name"].lower()
            == (manifest["owner"] + "/" + manifest["repository_name"]).lower()
        )
        assert manifest["repository_id"] in (
            None,
            item["id"],
        ), "Repository ID changed; refusing ownership"
        manifest["repository_id"] = item["id"]
    save(path, manifest)


def public_result(output):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", output):
        try:
            value, _ = decoder.raw_decode(output[match.start() :])
            message = value.get("msg") if isinstance(value, dict) else None
            parsed = json.loads(message) if isinstance(message, str) else message
            if isinstance(parsed, dict) and "project" in parsed:
                return parsed
        except (ValueError, TypeError):
            continue
    raise AssertionError("Public Role result was not returned")


def variables(manifest, name=None, source="none"):
    values = {
        "vercel_project_name": name or manifest["main"],
        "vercel_scope_type": manifest["scope_type"],
        "vercel_scope_id": manifest["scope_id"],
        "vercel_source_mode": source,
    }
    if source != "none":
        values.update(
            github_owner=manifest["owner"],
            github_repository=manifest["repository_name"],
        )
    return values


def run(path, manifest, values, check=False, expected_changes=None):
    try:
        result = invoke(
            values,
            role=ROLE,
            check=check,
            timeout=1200,
            tasks_after=[
                {
                    "name": "Return public acceptance result",
                    "ansible.builtin.debug": {
                        "msg": "{{ vercel_project_result | to_json }}"
                    },
                }
            ],
        )
        for key in ("VERCEL_TOKEN", "GH_TOKEN"):
            assert (
                os.environ[key] not in result.stdout
            ), "Credential appeared in execution output"
        assert result.returncode == 0, result.stdout
        if expected_changes is not None:
            assert changed(result) == expected_changes, result.stdout
        return public_result(result.stdout)
    finally:
        capture(path, manifest)


def prepare(path):
    if path.exists():
        raise RuntimeError(
            "Retained live manifest exists; clean it up before starting another run"
        )
    required = (
        "VERCEL_TOKEN",
        "GH_TOKEN",
        "VERCEL_TEST_SCOPE_TYPE",
        "VERCEL_TEST_SCOPE_ID",
        "GITHUB_TEST_OWNER",
    )
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError(
            "Set all protected live-test credentials and owner/scope variables"
        )
    scope_type = os.environ["VERCEL_TEST_SCOPE_TYPE"]
    assert scope_type in ("personal", "team")
    scope_id = os.environ["VERCEL_TEST_SCOPE_ID"]
    identity = request(
        "vercel",
        (
            "/v2/user"
            if scope_type == "personal"
            else "/v2/teams/" + quote(scope_id, safe="")
        ),
    )
    assert (
        identity is not None and (identity.get("user", identity)).get("id") == scope_id
    ), "Explicit Vercel identity inaccessible"
    prefix = "ansible-live-" + uuid.uuid4().hex[:20]
    main, sentinel, empty = (
        prefix + "-" + suffix for suffix in ("main", "sentinel", "empty")
    )
    manifest = {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "owner": os.environ["GITHUB_TEST_OWNER"],
        "repository_name": main,
        "repository_id": None,
        "main": main,
        "sentinel": sentinel,
        "empty": empty,
        "projects": {main: None, sentinel: None, empty: None},
        "started_ms": int(time.time() * 1000),
    }
    assert all(
        project(manifest, name) is None for name in manifest["projects"]
    ), "Allocated Project already exists"
    assert repository(manifest) is None, "Allocated repository already exists"
    save(path, manifest)
    run(path, manifest, variables(manifest, sentinel))
    run(path, manifest, variables(manifest, empty))
    run(path, manifest, variables(manifest, empty), expected_changes=0)


def seed(manifest, text, previous_sha=None):
    body = {
        "message": "Live acceptance fixture",
        "content": base64.b64encode(text.encode()).decode(),
    }
    if previous_sha:
        body["sha"] = previous_sha
    response = request(
        "github",
        "/repos/"
        + manifest["owner"]
        + "/"
        + manifest["repository_name"]
        + "/contents/public/index.html",
        "PUT",
        body,
    )
    return response["commit"]["sha"], response["content"]["sha"]


def verify(path, manifest):
    sentinel_before = project(manifest, manifest["sentinel"])
    main = variables(manifest, source="ensure")
    run(path, manifest, main, expected_changes=0)
    run(path, manifest, variables(manifest, source="existing"), expected_changes=0)
    repo = repository(manifest)
    assert repo and repo["private"] is True, "Test repository must be private"
    assert (
        request(
            "github",
            "/repos/"
            + manifest["owner"]
            + "/"
            + manifest["repository_name"]
            + "/contents/public/index.html",
        )
        is None
    )
    initial = project(manifest, manifest["main"])
    preview = dict(main, vercel_project_settings={"buildCommand": "echo acceptance"})
    run(path, manifest, preview, check=True)
    assert project(manifest, manifest["main"]) == initial, "Check mode mutated Project"
    run(path, manifest, preview)
    configured = project(manifest, manifest["main"])
    assert configured.get("buildCommand") == "echo acceptance"
    for key in ("installCommand", "framework", "rootDirectory", "outputDirectory"):
        assert configured.get(key) == initial.get(key), "Unspecified setting changed"
    sha_a, file_sha = seed(manifest, "<h1>Acceptance A</h1>\n")
    deploy = dict(main, vercel_deploy=True, vercel_git_sha=sha_a)
    result = run(path, manifest, deploy)
    assert result.get("deployment"), "Ready production Deployment result missing"
    assert_production(manifest, sha_a, result)
    run(path, manifest, deploy, expected_changes=0)
    sha_b, _ = seed(manifest, "<h1>Acceptance B</h1>\n", file_sha)
    result_b = run(path, manifest, dict(deploy, vercel_git_sha=sha_b))
    assert_production(manifest, sha_b, result_b)
    restored = run(
        path, manifest, deploy
    )  # Reuse historical A and make it production again.
    assert_production(manifest, sha_a, restored)
    assert (
        restored["deployment"]["id"] == result["deployment"]["id"]
    ), "Historical deployment was rebuilt"
    run(path, manifest, deploy, expected_changes=0)
    assert (
        project(manifest, manifest["sentinel"]) == sentinel_before
    ), "Unrelated Project changed"
    assert (
        project(manifest, manifest["empty"]) is not None
    ), "Empty Project unexpectedly removed"
    print(
        "Vercel/GitHub creation, reuse, private repository, check mode, exact commits, historical production reuse, and preservation passed"
    )


def assert_production(manifest, sha, result):
    deployment = result["deployment"]
    assert deployment["sha"] == sha and deployment["active"] is True
    assert deployment["state"] == "READY" and deployment["url"]
    actual = project(manifest, manifest["main"])
    assert (
        actual["targets"]["production"]["id"] == deployment["id"]
    ), "Requested Deployment is not active production"
    details = request(
        "vercel",
        scoped(manifest, "/v13/deployments/" + quote(deployment["id"], safe="")),
    )
    actual_sha = details.get("gitSource", {}).get("sha") or details.get("meta", {}).get(
        "githubCommitSha"
    )
    assert (
        actual_sha == sha
    ), "Provider's production commit differs from the requested SHA"


def cleanup(path, manifest):
    capture(path, manifest)
    failures = []
    for name, expected_id in manifest["projects"].items():
        try:
            current = project(manifest, name)
            if current is None:
                continue
            assert (
                expected_id and current["id"] == expected_id
            ), "Project ID changed; refusing deletion"
            request(
                "vercel",
                scoped(manifest, "/v9/projects/" + quote(expected_id, safe="")),
                "DELETE",
            )
            assert project(manifest, name) is None, "Project deletion not confirmed"
        except Exception as error:
            failures.append(str(error))
    try:
        repo = repository(manifest)
        if repo is not None:
            assert (
                manifest["repository_id"] and repo["id"] == manifest["repository_id"]
            ), "Repository ID changed; refusing deletion"
            request(
                "github",
                "/repos/" + manifest["owner"] + "/" + manifest["repository_name"],
                "DELETE",
            )
            assert repository(manifest) is None, "Repository deletion not confirmed"
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
            run(path, manifest, variables(manifest, source="ensure"))
        elif action == "verify":
            verify(path, manifest)
        elif action == "cleanup":
            cleanup(path, manifest)
        else:
            raise RuntimeError("Unknown acceptance action")


if __name__ == "__main__":
    main()
