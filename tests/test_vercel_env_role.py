"""Public installed Vercel env Role contracts at the CLI boundary."""

import json
import os
import shutil
from pathlib import Path

import pytest

from runner import changed, invoke

ROLE = "madebyphunky.vercel.env"


@pytest.fixture
def vercel_env(installed, tmp_path):
    state = tmp_path / "provider.json"
    state.write_text(
        json.dumps(
            {
                "calls": [],
                "project": {
                    "id": "prj_test",
                    "name": "test-project",
                    "accountId": "team_test",
                    "targets": {},
                },
                "envs": [],
            }
        )
    )
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
    )
    variables = {
        "vercel_project_name": "test-project",
        "vercel_scope_type": "team",
        "vercel_scope_id": "team_test",
        "vercel_manage_prerequisites": False,
        "vercel_npx_executable": str(tools / "npx"),
        "vercel_env": {
            "NEXT_PUBLIC_SUPABASE_URL": "https://abcdefghijabcdefghij.supabase.co",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
        },
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
            tasks_after=kwargs.pop(
                "tasks_after",
                [
                    {
                        "name": "Read public env result",
                        "ansible.builtin.debug": {"var": "vercel_env_result"},
                    }
                ],
            ),
            **kwargs
        )

    return run, read, write


def test_env_creates_production_variables_and_redacts_secrets(vercel_env):
    run, read, _ = vercel_env
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert "sb_secret_test_value" not in result.stdout
    assert "dummy-vercel" not in result.stdout
    envs = {item["key"]: item for item in read()["envs"]}
    assert set(envs) == {
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
    }
    assert envs["SUPABASE_SECRET_KEY"]["target"] == ["production"]
    assert envs["SUPABASE_SECRET_KEY"]["type"] == "sensitive"
    assert envs["NEXT_PUBLIC_SUPABASE_URL"]["type"] == "encrypted"
    assert all(item["target"] == ["production"] for item in read()["envs"])
    assert not any(
        "preview" in call.get("body", {})
        if isinstance(call.get("body"), dict)
        else "preview"
        in json.dumps(call.get("body") or [])
        for call in read()["calls"]
        if call["method"] in ("POST", "PATCH")
    )


def test_env_idempotent_when_production_values_match(vercel_env):
    run, read, write = vercel_env
    write(
        {
            "calls": [],
            "project": {
                "id": "prj_test",
                "name": "test-project",
                "accountId": "team_test",
            },
            "envs": [
                {
                    "id": "env_url",
                    "key": "NEXT_PUBLIC_SUPABASE_URL",
                    "value": "https://abcdefghijabcdefghij.supabase.co",
                    "target": ["production"],
                    "type": "encrypted",
                },
                {
                    "id": "env_pub",
                    "key": "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
                    "value": "sb_publishable_test",
                    "target": ["production"],
                    "type": "encrypted",
                },
                {
                    "id": "env_secret",
                    "key": "SUPABASE_SECRET_KEY",
                    "value": None,
                    "target": ["production"],
                    "type": "sensitive",
                },
            ],
        }
    )
    result = run()
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0
    assert not any(call["method"] in ("POST", "PATCH") for call in read()["calls"])


def test_env_preserves_unmanaged_remote_variables(vercel_env):
    run, read, write = vercel_env
    write(
        {
            "calls": [],
            "project": {
                "id": "prj_test",
                "name": "test-project",
                "accountId": "team_test",
            },
            "envs": [
                {
                    "id": "env_other",
                    "key": "UNRELATED_FLAG",
                    "value": "keep-me",
                    "target": ["production"],
                    "type": "encrypted",
                }
            ],
        }
    )
    result = run()
    assert result.returncode == 0, result.stdout
    keys = {item["key"] for item in read()["envs"]}
    assert "UNRELATED_FLAG" in keys
    assert "SUPABASE_SECRET_KEY" in keys


def test_env_rejects_preview_target(vercel_env):
    run, read, _ = vercel_env
    result = run(overrides={"vercel_env_target": "preview"})
    assert result.returncode != 0
    assert "production" in result.stdout.lower()
    assert read()["calls"] == [] or all(
        call["method"] == "GET" for call in read()["calls"]
    )


def test_env_check_mode_never_invokes_cli(vercel_env):
    run, read, _ = vercel_env
    result = run(check=True)
    assert result.returncode == 0, result.stdout
    assert "inspection_limited" in result.stdout
    assert read()["calls"] == []
