"""Public installed Vercel Role contracts at the CLI boundary, without credentials."""

import json
import os
import shutil
from pathlib import Path

import pytest

from runner import changed, invoke

SHA_A = "a" * 40
SHA_B = "b" * 40
ROLE = "madebyphunky.vercel.project"


@pytest.fixture
def vercel(installed, tmp_path):
    state = tmp_path / "provider.json"
    state.write_text(json.dumps({"calls": [], "commits": [SHA_A, SHA_B]}))
    tools = tmp_path / "bin"
    tools.mkdir()
    fixture = Path(__file__).parent / "fixtures/vercel_cli.py"
    for name in ("npx", "gh"):
        shutil.copyfile(fixture, tools / name)
        (tools / name).chmod(0o755)
    env = os.environ.copy()
    env.update(
        ANSIBLE_COLLECTIONS_PATH=str(installed),
        VERCEL_CONTRACT_STATE=str(state),
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_LOCALHOST_WARNING="False",
        ANSIBLE_PYTHON_INTERPRETER=os.sys.executable,
        VERCEL_TOKEN="dummy-vercel",
        GH_TOKEN="dummy-github",
    )
    variables = {
        "vercel_project_name": "test-project",
        "vercel_scope_type": "team",
        "vercel_scope_id": "team_test",
        "vercel_manage_prerequisites": False,
        "vercel_npx_executable": str(tools / "npx"),
        "vercel_gh_executable": str(tools / "gh"),
        "vercel_poll_interval": 1,
    }

    def read():
        return json.loads(state.read_text())

    def write(data):
        state.write_text(json.dumps(data))

    def run(overrides=None, **kwargs):
        return invoke(
            variables | (overrides or {}),
            env=env,
            role=ROLE,
            tasks_after=[
                {
                    "name": "Read public Project result",
                    "ansible.builtin.debug": {"var": "vercel_project_result"},
                }
            ],
            **kwargs
        )

    return run, variables, env, read, write


def source(variables, mode="existing"):
    variables.update(
        vercel_source_mode=mode, github_owner="tester", github_repository="demo"
    )


def repository():
    return {
        "id": 101,
        "full_name": "tester/demo",
        "private": True,
        "html_url": "https://github.com/tester/demo",
    }


def test_empty_project_creation_reuse_and_explicit_scope(vercel):
    run, _, _, read, _ = vercel
    first = run()
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert '"id": "prj_test"' in first.stdout
    assert read()["project"]["name"] == "test-project"
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert all(
        call["query"].get("teamId") == ["team_test"]
        for call in read()["calls"]
        if call["provider"] == "vercel"
    )
    assert not any(call["provider"] == "github" for call in read()["calls"])


def test_settings_update_only_supplied_fields(vercel):
    run, _, _, read, write = vercel
    assert (
        run(
            {
                "vercel_project_settings": {
                    "framework": "nextjs",
                    "installCommand": "npm ci",
                }
            }
        ).returncode
        == 0
    )
    result = run({"vercel_project_settings": {"buildCommand": "npm run build"}})
    assert result.returncode == 0, result.stdout
    assert read()["project"]["framework"] == "nextjs"
    assert read()["project"]["installCommand"] == "npm ci"
    assert read()["project"]["buildCommand"] == "npm run build"
    assert (
        changed(run({"vercel_project_settings": {"buildCommand": "npm run build"}}))
        == 0
    )


@pytest.mark.parametrize("owner_type", ["User", "Organization"])
def test_ensure_private_empty_repository_and_link_repeat_safety(vercel, owner_type):
    run, variables, _, read, write = vercel
    source(variables, "ensure")
    data = read()
    data["owner_type"] = owner_type
    write(data)
    result = run()
    assert result.returncode == 0, result.stdout
    assert read()["repository"]["private"] is True
    repo_calls = [
        call
        for call in read()["calls"]
        if call["provider"] == "github" and call["method"] == "POST"
    ]
    assert len(repo_calls) == 1
    assert repo_calls[0]["body"]["auto_init"] is False
    assert read()["project"]["link"] == {
        "type": "github",
        "org": "tester",
        "repo": "demo",
    }
    result = run()
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0


def test_existing_repository_link_and_unrelated_visibility_preserved(vercel):
    run, variables, _, read, write = vercel
    assert run().returncode == 0
    source(variables)
    data = read()
    data["repository"] = repository() | {"private": False}
    write(data)
    result = run()
    assert result.returncode == 0, result.stdout
    assert read()["repository"]["private"] is False
    assert read()["project"]["link"]["repo"] == "demo"
    assert changed(result) == 1


def test_conflicting_repository_link_fails_before_mutation(vercel):
    run, variables, _, read, write = vercel
    assert run().returncode == 0
    data = read()
    data["project"]["link"] = {"type": "github", "org": "other", "repo": "unrelated"}
    data["calls"] = []
    write(data)
    source(variables, "ensure")
    result = run()
    assert result.returncode != 0
    assert "refusing to relink" in result.stdout
    assert all(call["method"] == "GET" for call in read()["calls"])


def test_scope_mismatch_never_changes_existing_or_creates_resources(vercel):
    run, _, _, read, write = vercel
    data = read()
    data["team_id"] = "team_other"
    write(data)
    result = run()
    assert result.returncode != 0
    assert all(call["method"] == "GET" for call in read()["calls"])
    assert "project" not in read()


def test_personal_scope_checks_authenticated_user(vercel):
    run, variables, _, read, write = vercel
    variables.update(vercel_scope_type="personal", vercel_scope_id="user_test")
    data = read()
    data["account_id"] = "user_test"
    write(data)
    result = run()
    assert result.returncode == 0, result.stdout
    assert read()["calls"][0]["path"] == "/v2/user"
    assert all("teamId" not in call["query"] for call in read()["calls"])


@pytest.mark.parametrize(
    "override",
    [
        {"vercel_project_name": "UPPER"},
        {"vercel_source_mode": "existing"},
        {"vercel_deploy": True, "vercel_git_sha": SHA_A},
        {"vercel_project_settings": {"unknown": "value"}},
        {"vercel_project_settings": {"buildCommand": 4}},
        {"vercel_deployment_timeout": 0},
        {"VERCEL_TOKEN": ""},
    ],
)
def test_invalid_input_fails_before_any_client_or_installation(vercel, override):
    run, variables, _, read, _ = vercel
    # Keep prerequisite management enabled: these inputs must fail before any installer runs.
    variables["vercel_manage_prerequisites"] = True
    result = run(override)
    assert result.returncode != 0
    assert read()["calls"] == []


def test_check_mode_never_launches_or_downloads_clients(vercel):
    run, variables, _, read, _ = vercel
    variables.update(
        vercel_npx_executable="/does/not/exist", vercel_gh_executable="/does/not/exist"
    )
    result = run(check=True)
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert '"inspection_limited": true' in result.stdout
    assert read()["calls"] == []


def test_explicit_credentials_override_environment_and_all_output_is_redacted(vercel):
    run, variables, env, _, _ = vercel
    variables.update(
        VERCEL_TOKEN="explicit-vercel-secret", GH_TOKEN="explicit-github-secret"
    )
    env["VERCEL_CONTRACT_EXPECT_VERCEL"] = "explicit-vercel-secret"
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert "explicit-vercel-secret" not in result.stdout
    assert "explicit-github-secret" not in result.stdout
    env["VERCEL_CONTRACT_EXPECT_VERCEL"] = "denied"
    result = run(verbose=True)
    assert result.returncode != 0
    assert "explicit-vercel-secret" not in result.stdout


def test_production_deployment_reuses_exact_sha_and_promotes_history(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    data = read()
    data["repository"] = repository()
    write(data)
    result = run()
    assert result.returncode == 0, result.stdout
    assert read()["project"]["targets"]["production"]["id"] == "dpl_1"
    assert len(read()["deployments"]) == 1
    result = run()
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0
    assert len(read()["deployments"]) == 1
    assert run({"vercel_git_sha": SHA_B}).returncode == 0
    result = run()
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert len(read()["deployments"]) == 2
    assert read()["project"]["targets"]["production"]["id"] == "dpl_1"
    assert '"active": true' in result.stdout
    assert any("/promote/dpl_1" in call["path"] for call in read()["calls"])


def test_changed_build_settings_need_a_new_deployment(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    data = read()
    data["repository"] = repository()
    write(data)
    assert run().returncode == 0
    result = run({"vercel_project_settings": {"buildCommand": "npm run build"}})
    assert result.returncode == 0, result.stdout
    assert len(read()["deployments"]) == 2


def test_pending_deployment_is_awaited_not_duplicated(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    data = read()
    data["repository"] = repository()
    write(data)
    assert run().returncode == 0
    data = read()
    data["deployments"][0]["readyState"] = "BUILDING"
    data["finish_pending"] = True
    write(data)
    result = run()
    assert result.returncode == 0, result.stdout
    assert len(read()["deployments"]) == 1
    assert changed(result) == 0


def test_failed_deployment_requires_explicit_retry_and_retains_ids(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    data = read()
    data.update(
        repository=repository(),
        new_deployment_state="ERROR",
        deployment_error_message="Fixture build command failed",
    )
    write(data)
    result = run()
    assert result.returncode != 0
    assert read()["project"]["id"] == "prj_test"
    assert read()["deployments"][0]["id"] == "dpl_1"
    assert "Fixture build command failed" in result.stdout
    assert "dpl_1" in result.stdout
    result = run()
    assert result.returncode != 0
    assert "vercel_retry_failed_deployment" in result.stdout
    assert len(read()["deployments"]) == 1
    data = read()
    data["new_deployment_state"] = "READY"
    write(data)
    result = run({"vercel_retry_failed_deployment": True})
    assert result.returncode == 0, result.stdout
    assert len(read()["deployments"]) == 2


def test_timeout_preserves_created_resources(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(
        vercel_deploy=True, vercel_git_sha=SHA_A, vercel_deployment_timeout=2
    )
    data = read()
    data.update(repository=repository(), new_deployment_state="BUILDING")
    write(data)
    result = run()
    assert result.returncode != 0
    assert "timeout" in result.stdout.lower() or "timed out" in result.stdout.lower()
    assert read()["project"]["id"] == "prj_test"
    assert read()["deployments"][0]["id"] == "dpl_1"
    assert not any(call["method"] == "DELETE" for call in read()["calls"])


def test_ensure_with_deploy_does_not_create_empty_missing_repository(vercel):
    run, variables, _, read, _ = vercel
    source(variables, "ensure")
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    result = run()
    assert result.returncode != 0
    assert all(call["method"] == "GET" for call in read()["calls"])
    assert "repository" not in read()


def test_missing_existing_repository_fails_before_project_creation(vercel):
    run, variables, _, read, _ = vercel
    source(variables)
    result = run()
    assert result.returncode != 0
    assert "existing GitHub repository was not found" in result.stdout
    assert all(call["method"] == "GET" for call in read()["calls"])


def test_github_app_failure_retains_new_repository_without_deleting_it(vercel):
    run, variables, _, read, write = vercel
    source(variables, "ensure")
    data = read()
    data["app_access_denied"] = True
    write(data)
    result = run()
    assert result.returncode != 0
    assert "Vercel GitHub App" in result.stdout
    assert read()["repository"]["full_name"] == "tester/demo"
    assert "project" not in read()
    assert not any(call["method"] == "DELETE" for call in read()["calls"])


def test_disabled_deployment_leaves_active_version_alone(vercel):
    run, variables, _, read, write = vercel
    source(variables)
    variables.update(vercel_deploy=True, vercel_git_sha=SHA_A)
    data = read()
    data["repository"] = repository()
    write(data)
    assert run().returncode == 0
    before = read()["project"]["targets"]
    result = run({"vercel_deploy": False, "vercel_git_sha": SHA_B})
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0
    assert len(read()["deployments"]) == 1
    assert read()["project"]["targets"] == before
