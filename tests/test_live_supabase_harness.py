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


def test_operator_recovery_deletes_only_the_confirmed_ref(monkeypatch):
    data = manifest()
    ref = "abcdefghijabcdefghij"
    state = {
        "project": {
            "ref": ref,
            "name": data["main"],
            "organization_id": data["organization_id"],
        }
    }
    monkeypatch.setattr(
        live, "projects", lambda: [state["project"]] if state["project"] else []
    )
    calls = []

    def request(endpoint, method="GET", body=None):
        calls.append((endpoint, method))
        state["project"] = None

    monkeypatch.setattr(live, "request", request)
    live.recover_confirmed_project(data, ref)
    assert calls == [("/v1/projects/" + ref, "DELETE")]


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "unrelated"),
        ("organization_id", "other"),
        ("ref", "zzzzzzzzzzzzzzzzzzzz"),
    ],
)
def test_operator_recovery_rejects_identity_mismatch(monkeypatch, field, value):
    data = manifest()
    row = {
        "ref": "abcdefghijabcdefghij",
        "name": data["main"],
        "organization_id": data["organization_id"],
    }
    row[field] = value
    monkeypatch.setattr(live, "projects", lambda: [row])
    monkeypatch.setattr(
        live, "request", lambda *_: pytest.fail("Deletion must not occur")
    )
    with pytest.raises(AssertionError):
        live.recover_confirmed_project(data, "abcdefghijabcdefghij")


def test_recovery_confirms_inventory_absence_when_deleted_ref_returns_403(monkeypatch):
    data = manifest()
    ref = "abcdefghijabcdefghij"
    state = {
        "row": {
            "ref": ref,
            "name": data["main"],
            "organization_id": data["organization_id"],
        }
    }

    def by_ref(_):
        if state["row"] is None:
            raise RuntimeError("supabase GET project returned HTTP 403")
        return state["row"]

    monkeypatch.setattr(live, "project_by_ref", by_ref)
    monkeypatch.setattr(
        live, "projects", lambda: [state["row"]] if state["row"] else []
    )

    def request(endpoint, method="GET", body=None):
        assert (endpoint, method) == ("/v1/projects/" + ref, "DELETE")
        state["row"] = None

    monkeypatch.setattr(live, "request", request)
    live.recover_confirmed_project(data, ref)
    assert state["row"] is None


def test_unset_fixture_path_initializes_auth_and_migrations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUPABASE_TEST_SMTP_PASS", raising=False)
    data = manifest()
    root = live.fixture_dir(data)
    assert root != tmp_path
    assert (root / "supabase/config.toml").is_file()
    assert (root / "supabase/migrations/20261102190000_widgets.sql").is_file()
    assert data["fixture_dir"] == str(root)
    assert live.fixture_dir(data) == root


def test_live_verification_does_not_skip_database_permission_failure(
    tmp_path, monkeypatch
):
    import subprocess

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "dummy-token")
    monkeypatch.setenv("SUPABASE_TEST_PASSWORD", "dummy-password")
    monkeypatch.delenv("SUPABASE_TEST_SMTP_PASS", raising=False)
    data = manifest()
    ref = data["projects"][data["main"]]
    path = tmp_path / "manifest.json"
    live.save(path, data)
    monkeypatch.setattr(live, "capture", lambda *_: None)
    monkeypatch.setattr(
        live,
        "request",
        lambda *_: {
            "external_email_enabled": True,
            "site_url": "https://acceptance.example.test",
            "uri_allow_list": "https://acceptance.example.test/callback",
        },
    )
    monkeypatch.setattr(live, "project", lambda *_: {"ref": ref})
    monkeypatch.setattr(
        live,
        "run_role",
        lambda *_args, **_kwargs: {"project": {"ref": ref, "status": "ACTIVE_HEALTHY"}},
    )
    monkeypatch.setattr(
        live,
        "invoke",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, stdout="conflict"),
    )
    monkeypatch.setattr(
        live.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout="3.0.0", stderr=""
        ),
    )

    def denied(*_):
        raise RuntimeError("supabase query returned HTTP 403")

    monkeypatch.setattr(live, "sql", denied)
    with pytest.raises(RuntimeError, match="HTTP 403"):
        live.verify(path, data)


def test_fixture_paths_work_from_ansible_execution_directory(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUPABASE_TEST_SMTP_PASS", raising=False)
    data = manifest()
    root = live.fixture_dir(data)
    execution = tmp_path / "ansible-home"
    execution.mkdir()
    monkeypatch.chdir(execution)
    assert root.is_absolute()
    assert Path(data["auth_config"]).is_file()
    assert (Path(data["fixture_dir"]) / "supabase/migrations").is_dir()


def test_live_verification_rejects_changed_omitted_auth_setting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "dummy-token")
    monkeypatch.setenv("SUPABASE_TEST_PASSWORD", "dummy-password")
    monkeypatch.delenv("SUPABASE_TEST_SMTP_PASS", raising=False)
    data = manifest()
    ref = data["projects"][data["main"]]
    path = tmp_path / "manifest.json"
    live.save(path, data)
    monkeypatch.setattr(live, "capture", lambda *_: None)
    monkeypatch.setattr(live, "project", lambda *_: {"ref": ref})
    monkeypatch.setattr(
        live,
        "run_role",
        lambda *_args, **_kwargs: {"project": {"ref": ref, "status": "ACTIVE_HEALTHY"}},
    )
    responses = iter(
        [
            {"external_email_enabled": True},
            {
                "external_email_enabled": False,
                "site_url": "https://acceptance.example.test",
                "uri_allow_list": "https://acceptance.example.test/callback",
            },
        ]
    )
    monkeypatch.setattr(live, "request", lambda *_: next(responses))
    with pytest.raises(AssertionError, match="Omitted Auth configuration"):
        live.verify(path, data)
