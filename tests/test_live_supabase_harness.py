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


def test_confirmed_creation_records_ownership_despite_old_provider_timestamp(
    tmp_path, monkeypatch
):
    """Replay the live run: a successful create followed by capture rejecting its age."""
    import subprocess

    data = manifest()
    name = data["main"]
    ref = "abcdefghijabcdefghij"
    data["projects"] = {name: None}
    data["initial_absence"] = [name]
    data["started_ms"] = 1793705117331
    path = tmp_path / "manifest.json"
    live.save(path, data)
    row = {
        "ref": ref,
        "name": name,
        "organization_id": data["organization_id"],
        "created_at": "2026-11-03T09:27:50.384392Z",
    }
    output = "ok: [localhost] => " + json.dumps(
        {"msg": json.dumps({"creation_attempted": True, "project": row})}
    )
    monkeypatch.setattr(
        live,
        "invoke",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout=output),
    )
    monkeypatch.setattr(live, "project", lambda *_: row)
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "dummy-token")
    monkeypatch.setenv("SUPABASE_TEST_PASSWORD", "dummy-password")
    result = live.run_role(path, data, live.PROJECT, {"supabase_project_name": name})
    assert result["project"]["ref"] == ref
    assert json.loads(path.read_text())["projects"][name] == ref


def test_old_project_without_creation_receipt_is_not_claimed(tmp_path, monkeypatch):
    data = manifest()
    data["started_ms"] = 1793705117331
    data["projects"] = {data["main"]: None}
    data["initial_absence"] = [data["main"]]
    path = tmp_path / "manifest.json"
    live.save(path, data)
    monkeypatch.setattr(
        live,
        "project",
        lambda *_: {
            "ref": "abcdefghijabcdefghij",
            "name": data["main"],
            "organization_id": data["organization_id"],
            "created_at": "2026-11-03T09:27:50.384392Z",
        },
    )
    with pytest.raises(AssertionError, match="Pre-existing Project"):
        live.capture(path, data)
    assert json.loads(path.read_text())["projects"][data["main"]] is None


def test_cleanup_uses_confirmed_receipt_with_older_timestamp(tmp_path, monkeypatch):
    data = manifest()
    name = data["main"]
    ref = data["projects"][name]
    data["initial_absence"] = [name]
    data["creation_receipts"] = {name: ref}
    data["started_ms"] = 1793705117331
    path = tmp_path / "manifest.json"
    live.save(path, data)
    state = {
        "project": {
            "ref": ref,
            "name": name,
            "organization_id": data["organization_id"],
            "created_at": "2026-11-03T09:27:50.384392Z",
        }
    }
    monkeypatch.setattr(live, "project", lambda *_: state["project"])
    deleted = []

    def request(endpoint, method="GET", body=None):
        assert method == "DELETE"
        deleted.append(endpoint)
        state["project"] = None

    monkeypatch.setattr(live, "request", request)
    live.cleanup(path, data)
    assert deleted == ["/v1/projects/" + ref]
    assert not path.exists()


def test_receipt_does_not_allow_replacement_or_missing_absence(tmp_path, monkeypatch):
    data = manifest()
    name = data["main"]
    ref = data["projects"][name]
    data["creation_receipts"] = {name: ref}
    path = tmp_path / "manifest.json"
    live.save(path, data)
    row = {
        "ref": ref,
        "name": name,
        "organization_id": data["organization_id"],
        "created_at": "1970-01-01T00:00:02Z",
    }
    monkeypatch.setattr(live, "project", lambda *_: row)
    with pytest.raises(AssertionError, match="Initial absence"):
        live.capture(path, data)
    data["initial_absence"] = [name]
    row["ref"] = "zzzzzzzzzzzzzzzzzzzz"
    with pytest.raises(AssertionError, match="reference changed"):
        live.capture(path, data)


def test_record_action_persists_receipt_before_capture(tmp_path, monkeypatch):
    data = manifest()
    name = data["main"]
    data["projects"][name] = None
    data["initial_absence"] = [name]
    path = tmp_path / "manifest.json"
    live.save(path, data)
    public = {
        "creation_attempted": True,
        "project": {
            "ref": "abcdefghijabcdefghij",
            "name": name,
            "organization_id": data["organization_id"],
        },
    }
    monkeypatch.setattr(
        live.sys, "argv", ["live", "record", str(path), json.dumps(public)]
    )
    live.main()
    assert (
        json.loads(path.read_text())["creation_receipts"][name]
        == "abcdefghijabcdefghij"
    )
