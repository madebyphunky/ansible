"""Cleanup identity guards for the live harness; no cloud access."""

import json

import pytest

import live_vercel_acceptance as live


def manifest():
    return {
        "scope_type": "team",
        "scope_id": "team-test",
        "owner": "test-owner",
        "repository_name": "allocated-repo",
        "repository_id": 17,
        "projects": {"allocated-project": "prj-17"},
        "started_ms": 1000,
    }


def test_public_result_parser_ignores_other_callback_objects():
    output = 'ok: [localhost] => {"changed": false}\nok: [localhost] => {"msg": "{\\"project\\": {\\"id\\": \\"prj-17\\"}, \\"deployment\\": null}"}'
    assert live.public_result(output)["project"]["id"] == "prj-17"


def test_cleanup_refuses_replacement_resource_and_preserves_manifest(
    tmp_path, monkeypatch
):
    data = manifest()
    path = tmp_path / "manifest.json"
    live.save(path, data)
    monkeypatch.setattr(
        live,
        "project",
        lambda *_: {
            "id": "prj-replacement",
            "name": "allocated-project",
            "accountId": "team-test",
            "createdAt": 2000,
        },
    )
    monkeypatch.setattr(
        live,
        "request",
        lambda *_args, **_kwargs: pytest.fail("Deletion must not occur"),
    )
    with pytest.raises(AssertionError, match="ID changed"):
        live.cleanup(path, data)
    assert json.loads(path.read_text())["projects"]["allocated-project"] == "prj-17"


def test_cleanup_deletes_only_verified_ids_and_retries_other_resources(
    tmp_path, monkeypatch
):
    data = manifest()
    path = tmp_path / "manifest.json"
    live.save(path, data)
    deleted = []
    state = {
        "project": {
            "id": "prj-17",
            "name": "allocated-project",
            "accountId": "team-test",
            "createdAt": 2000,
        },
        "repo": {
            "id": 17,
            "full_name": "test-owner/allocated-repo",
            "created_at": "1970-01-01T00:00:02Z",
        },
    }
    monkeypatch.setattr(live, "project", lambda *_: state["project"])
    monkeypatch.setattr(live, "repository", lambda *_: state["repo"])

    def request(provider, endpoint, method="GET", body=None):
        assert method == "DELETE"
        deleted.append((provider, endpoint))
        state["project" if provider == "vercel" else "repo"] = None

    monkeypatch.setattr(live, "request", request)
    live.cleanup(path, data)
    assert deleted == [
        ("vercel", "/v9/projects/prj-17?teamId=team-test"),
        ("github", "/repos/test-owner/allocated-repo"),
    ]
    assert not path.exists()


def test_failed_cleanup_keeps_manifest_and_attempts_repository(tmp_path, monkeypatch):
    data = manifest()
    path = tmp_path / "manifest.json"
    live.save(path, data)
    repo = {
        "id": 17,
        "full_name": "test-owner/allocated-repo",
        "created_at": "1970-01-01T00:00:02Z",
    }
    monkeypatch.setattr(
        live,
        "project",
        lambda *_: {
            "id": "prj-17",
            "name": "allocated-project",
            "accountId": "team-test",
            "createdAt": 2000,
        },
    )
    monkeypatch.setattr(live, "repository", lambda *_: repo or None)
    deleted = []

    def request(provider, endpoint, method="GET", body=None):
        if provider == "vercel":
            raise RuntimeError("Deletion unavailable")
        deleted.append(endpoint)
        repo.clear()

    monkeypatch.setattr(live, "request", request)
    with pytest.raises(RuntimeError, match="Cleanup incomplete"):
        live.cleanup(path, data)
    assert path.exists()
    assert deleted == ["/repos/test-owner/allocated-repo"]
