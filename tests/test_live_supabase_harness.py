"""Cleanup identity guards for the Supabase live harness; no cloud access."""

import json

import pytest

import live_supabase_acceptance as live


def manifest():
    return {
        "organization": "org-test",
        "organization_id": "org-test",
        "organization_slug": "org-test",
        "region": "eu-west-2",
        "main": "allocated-main",
        "sentinel": "allocated-sentinel",
        "projects": {"allocated-main": "abcdefghijabcdefghij"},
        "started_ms": 1000,
        "fixture_dir": None,
    }


def test_public_result_parser_ignores_other_callback_objects():
    output = (
        'ok: [localhost] => {"changed": false}\n'
        'ok: [localhost] => {"msg": "{\\"project\\": {\\"ref\\": \\"abcdefghijabcdefghij\\"}}"}'
    )
    assert live.public_result(output, "project")["project"]["ref"] == (
        "abcdefghijabcdefghij"
    )


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
            "ref": "zzzzzzzzzzzzzzzzzzzz",
            "id": "zzzzzzzzzzzzzzzzzzzz",
            "name": "allocated-main",
            "organization_id": "org-test",
            "created_at": "1970-01-01T00:00:02Z",
        },
    )
    monkeypatch.setattr(
        live,
        "request",
        lambda *_args, **_kwargs: pytest.fail("Deletion must not occur"),
    )
    with pytest.raises(AssertionError, match="reference changed"):
        live.cleanup(path, data)
    assert (
        json.loads(path.read_text())["projects"]["allocated-main"]
        == "abcdefghijabcdefghij"
    )


def test_cleanup_deletes_only_verified_refs(tmp_path, monkeypatch):
    data = manifest()
    path = tmp_path / "manifest.json"
    live.save(path, data)
    deleted = []
    state = {
        "project": {
            "ref": "abcdefghijabcdefghij",
            "id": "abcdefghijabcdefghij",
            "name": "allocated-main",
            "organization_id": "org-test",
            "created_at": "1970-01-01T00:00:02Z",
        }
    }
    monkeypatch.setattr(live, "project", lambda *_: state["project"])

    def request(endpoint, method="GET", body=None):
        assert method == "DELETE"
        deleted.append(endpoint)
        state["project"] = None

    monkeypatch.setattr(live, "request", request)
    live.cleanup(path, data)
    assert deleted == ["/v1/projects/abcdefghijabcdefghij"]
    assert not path.exists()


def test_failed_cleanup_keeps_manifest(tmp_path, monkeypatch):
    data = manifest()
    path = tmp_path / "manifest.json"
    live.save(path, data)
    monkeypatch.setattr(
        live,
        "project",
        lambda *_: {
            "ref": "abcdefghijabcdefghij",
            "id": "abcdefghijabcdefghij",
            "name": "allocated-main",
            "organization_id": "org-test",
            "created_at": "1970-01-01T00:00:02Z",
        },
    )

    def request(endpoint, method="GET", body=None):
        raise RuntimeError("Deletion unavailable")

    monkeypatch.setattr(live, "request", request)
    with pytest.raises(RuntimeError, match="Cleanup incomplete"):
        live.cleanup(path, data)
    assert path.exists()
