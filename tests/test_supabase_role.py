"""Installed public Supabase Role contracts at the noninteractive CLI boundary."""

import json
import os
from pathlib import Path
import shutil

import pytest

from runner import changed, invoke


@pytest.fixture
def supabase(installed, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"calls": []}))
    cli = tmp_path / "npx"
    shutil.copyfile(Path(__file__).parent / "fixtures/supabase_cli.py", cli)
    cli.chmod(0o755)
    config = tmp_path / "config.toml"
    config.write_text(
        '[auth]\nsite_url = "https://example.test"\nadditional_redirect_urls = []\n[storage]\nenabled = false\n'
    )
    checkout = tmp_path / "application"
    migrations = checkout / "supabase/migrations"
    migrations.mkdir(parents=True)
    (migrations / "20261102090000_widgets.sql").write_text(
        "create table widgets (id int);"
    )
    (checkout / "supabase/config.toml").write_text(
        '[vault.secrets]\nother = "never push this"\n'
    )
    env = os.environ.copy() | {
        "ANSIBLE_COLLECTIONS_PATH": str(installed),
        "ANSIBLE_NOCOLOR": "1",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_PYTHON_INTERPRETER": os.sys.executable,
        "ANSIBLE_SUPABASE_CONTRACT_STATE": str(state),
        "SUPABASE_ACCESS_TOKEN": "ambient-token-must-lose",
        "SUPABASE_AUTH_SITE_URL": "https://ambient-must-not-override.test",
    }
    variables = {
        "SUPABASE_ACCESS_TOKEN": "dummy-explicit-token",
        "SUPABASE_DB_PASSWORD": "dummy-db-password",
        "supabase_manage_prerequisites": False,
        "supabase_npx_executable": str(cli),
        "supabase_organization": "org-id",
        "supabase_project_name": "test-project",
        "supabase_region": "eu-west-2",
        "supabase_auth_config": str(config),
        "supabase_workdir": str(checkout),
        "supabase_poll_interval": 1,
    }

    def run(role="project", overrides=None, **kwargs):
        supplied = variables | (overrides or {})
        if role != "project":
            supplied.setdefault("supabase_project_ref", "testref")
        tasks = [
            {
                "name": "Inspect nonsecret public result",
                "ansible.builtin.debug": {"var": "supabase_" + role + "_result"},
            }
        ]
        if role == "project":
            tasks.append(
                {
                    "name": "Verify generated password stays separate from the public result",
                    "ansible.builtin.assert": {
                        "that": [
                            "not supabase_project_result.get('password_change_required', false) or supabase_project_initial_password | length >= 32",
                            "'initial_password' not in supabase_project_result",
                        ]
                    },
                }
            )
        return invoke(
            supplied,
            env=env,
            role="madebyphunky.supabase." + role,
            tasks_after=kwargs.pop("tasks_after", tasks),
            **kwargs
        )

    def read():
        return json.loads(state.read_text())

    def write(data):
        state.write_text(json.dumps(data))

    return run, read, write, config, checkout


def project(**extra):
    return {
        "ref": "testref",
        "id": "testref",
        "name": "test-project",
        "organization_id": "org-id",
        "organization_slug": "my-org",
        "region": "eu-west-2",
        "status": "ACTIVE_HEALTHY",
    } | extra


def test_project_create_reuse_and_generated_password_redaction(supabase):
    run, read, _, _, _ = supabase
    first = run(verbose=True)
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    secret = read()["password"]
    assert secret not in first.stdout
    assert "dummy-explicit-token" not in first.stdout
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert sum(call["operation"] == "projects create" for call in read()["calls"]) == 1
    assert read()["calls"][0]["version"] == "supabase@latest"


@pytest.mark.parametrize(
    "rows,overrides,error",
    [
        (
            [project(), project(ref="duplicate", id="duplicate")],
            {},
            "Multiple Projects",
        ),
        (
            [project(organization_id="other", organization_slug="other")],
            {"supabase_project_ref": "testref"},
            "different organization",
        ),
        ([project(region="us-east-1")], {}, "region differs"),
        (
            [project(name="other")],
            {"supabase_project_ref": "testref"},
            "different name",
        ),
        ([], {"supabase_project_ref": "missing"}, "must resolve"),
    ],
)
def test_project_identity_conflicts_fail_without_creation(
    supabase, rows, overrides, error
):
    run, read, write, _, _ = supabase
    write({"calls": [], "projects": rows})
    result = run(overrides=overrides)
    assert result.returncode != 0
    assert error in result.stdout
    assert all(call["operation"] != "projects create" for call in read()["calls"])


def test_explicit_ref_resolves_ambiguous_name_and_version_override(supabase):
    run, read, write, _, _ = supabase
    write({"projects": [project(), project(ref="another", id="another")]})
    result = run(
        overrides={"supabase_project_ref": "testref", "supabase_cli_version": "3.0.0"}
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0
    assert all(call["version"] == "supabase@3.0.0" for call in read()["calls"])


@pytest.mark.parametrize("role", ["project", "auth", "migrations"])
def test_check_mode_never_invokes_cli(supabase, role):
    run, read, _, _, _ = supabase
    result = run(role, check=True)
    assert result.returncode == 0, result.stdout
    assert "inspection_limited" in result.stdout
    assert read()["calls"] == []


def test_auth_sparse_config_preserves_omitted_fields_and_repeat_idempotency(supabase):
    run, read, write, _, _ = supabase
    write(
        {
            "auth": {
                "site_url": "https://old.test",
                "enable_signup": False,
                "external": {"github": {"enabled": True}},
            }
        }
    )
    first = run("auth", verbose=True)
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert read()["auth"]["enable_signup"] is False
    assert read()["auth"]["external"]["github"]["enabled"] is True
    assert read()["auth"]["additional_redirect_urls"] == []
    second = run("auth")
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert sum(call["operation"] == "config push" for call in read()["calls"]) == 1


def test_migrations_pending_only_no_checkout_changes(supabase):
    run, read, _, _, checkout = supabase
    before = {
        str(p.relative_to(checkout)): p.read_bytes()
        for p in checkout.rglob("*")
        if p.is_file()
    }
    first = run("migrations")
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    second = run("migrations")
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert read()["applied"] == ["20261102090000_widgets.sql"]
    after = {
        str(p.relative_to(checkout)): p.read_bytes()
        for p in checkout.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_migration_history_conflict_never_attempts_apply(supabase):
    run, read, write, _, _ = supabase
    write({"history_conflict": True})
    result = run("migrations")
    assert result.returncode != 0
    assert all("--dry-run" in call["args"] for call in read()["calls"])


def test_create_failure_is_not_retried_and_preserves_secret_without_logging(supabase):
    run, read, write, _, _ = supabase
    write({"fail_after_create": True})
    result = run(verbose=True)
    assert result.returncode != 0
    assert read()["password"] not in result.stdout
    assert sum(call["operation"] == "projects create" for call in read()["calls"]) == 1
    assert read()["projects"][0]["ref"] == "testref"


def test_project_readiness_timeout_retains_identity(supabase):
    run, read, write, _, _ = supabase
    write({"status": "COMING_UP"})
    result = run(overrides={"supabase_timeout": 3})
    assert result.returncode != 0
    assert read()["projects"][0]["ref"] == "testref"
    assert "readiness timed out" in result.stdout
    assert read()["password"] not in result.stdout


def test_invalid_auth_toml_fails_before_cli(supabase):
    run, read, _, config, _ = supabase
    config.write_text("[auth\n")
    result = run("auth")
    assert result.returncode != 0
    assert read()["calls"] == []


def test_declared_auth_secrets_use_push_comparison_and_remain_idempotent(supabase):
    run, read, _, config, _ = supabase
    config.write_text('[auth.email.smtp]\nenabled = true\npass = "dummy-smtp-secret"\n')
    first = run("auth", verbose=True)
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert "dummy-smtp-secret" not in first.stdout
    second = run("auth", verbose=True)
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert sum(call["operation"] == "config push" for call in read()["calls"]) == 2
    config.write_text(
        '[auth.email.smtp]\nenabled = true\npass = "new-dummy-smtp-secret"\n'
    )
    third = run("auth", verbose=True)
    assert third.returncode == 0, third.stdout
    assert changed(third) == 1
    assert "new-dummy-smtp-secret" not in third.stdout


@pytest.mark.parametrize("status", ["unavailable", "not_pushable", "disabled"])
def test_auth_unsuccessful_service_status_does_not_report_success(supabase, status):
    run, _, write, _, _ = supabase
    write({"push_status": status})
    result = run("auth")
    assert result.returncode != 0
    assert "could not apply" in result.stdout


def test_auth_missing_remote_scope_never_pushes(supabase):
    run, read, write, _, _ = supabase
    write({"missing_scope": ["auth"]})
    result = run("auth")
    assert result.returncode != 0
    assert all(call["operation"] != "config push" for call in read()["calls"])


def test_blank_explicit_token_fails_before_prerequisite_setup(supabase):
    run, read, _, _, _ = supabase
    result = run(
        overrides={"SUPABASE_ACCESS_TOKEN": "", "supabase_manage_prerequisites": True}
    )
    assert result.returncode != 0
    assert "Supply SUPABASE_ACCESS_TOKEN" in result.stdout
    assert "Ensure Node.js" not in result.stdout
    assert read()["calls"] == []


def test_composed_roles_pass_new_identity_and_password_without_logging(supabase):
    run, read, _, _, _ = supabase
    tasks = [
        {
            "name": "Compose Auth",
            "ansible.builtin.include_role": {"name": "madebyphunky.supabase.auth"},
            "vars": {
                "supabase_project_ref": "{{ supabase_project_result.project.ref }}"
            },
        },
        {
            "name": "Compose migrations",
            "ansible.builtin.include_role": {
                "name": "madebyphunky.supabase.migrations"
            },
            "vars": {
                "supabase_project_ref": "{{ supabase_project_result.project.ref }}",
                "SUPABASE_DB_PASSWORD": "{{ supabase_project_initial_password }}",
            },
        },
    ]
    result = run(tasks_after=tasks, verbose=True)
    assert result.returncode == 0, result.stdout
    assert read()["password"] not in result.stdout
    assert read()["applied"] == ["20261102090000_widgets.sql"]
