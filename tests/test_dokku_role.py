"""Contracts run the installed public Role through an SSH/Dokku double."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from runner import changed, invoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dokku(installed, tmp_path):
    executable = tmp_path / "ssh"
    executable.write_text((ROOT / "tests/fixtures/dokku_ssh.py").read_text())
    executable.chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"apps": [], "version": "0.38.34"}))
    variables = {
        "dokku_host": "203.0.113.10",
        "dokku_app": "billing",
        "dokku_ssh_executable": str(executable),
    }
    env = os.environ | {
        "ANSIBLE_COLLECTIONS_PATH": str(installed),
        "ANSIBLE_NOCOLOR": "1",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_PYTHON_INTERPRETER": os.sys.executable,
        "DOKKU_TEST_STATE": str(state),
    }

    def run(overrides=None, omit=(), **kwargs):
        values = variables | (overrides or {})
        for key in omit:
            values.pop(key, None)
        return invoke(
            values,
            env=env,
            role="madebyphunky.dokku.app",
            tasks_after=[
                {
                    "name": "Show the public result",
                    "ansible.builtin.debug": {"var": "dokku_app_result"},
                }
            ],
            **kwargs,
        )

    run.variables = variables
    run.env = env
    return run, state


def data(state):
    return json.loads(state.read_text())


def remote_commands(state):
    commands = []
    for call in data(state).get("calls", []):
        destination = next(
            index for index, arg in enumerate(call) if arg.startswith("dokku@")
        )
        commands.append(call[destination + 1 :])
    return commands


def public_result(completed):
    match = re.search(
        r'"dokku_app_result": (\{.*?\n    \})', completed.stdout, re.DOTALL
    )
    assert match, completed.stdout
    return json.loads(match.group(1))


@pytest.mark.parametrize(
    "overrides,omit",
    [
        ({"dokku_app": "Billing"}, ()),
        ({"dokku_app": ""}, ()),
        ({"dokku_app": "billing_staging"}, ()),
        ({"dokku_host": "-oProxyCommand=touch"}, ()),
        ({"dokku_host": "dokku@203.0.113.10"}, ()),
        ({"dokku_host": "203.0.113.10 extra"}, ()),
        ({"dokku_ssh_port": 0}, ()),
        ({}, ("dokku_host",)),
        ({}, ("dokku_app",)),
    ],
)
def test_invalid_inputs_fail_before_ssh(dokku, overrides, omit):
    run, state = dokku
    result = run(overrides, omit=omit)
    assert result.returncode != 0, result.stdout
    assert "was not found" not in result.stdout
    assert not data(state).get("calls")


def test_missing_app_is_created_and_then_reused(dokku):
    run, state = dokku
    first = run()
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert data(state)["apps"] == ["billing"]
    assert remote_commands(state) == [
        ["version"],
        ["apps:exists", "billing"],
        ["apps:create", "billing"],
    ]
    created = public_result(first)
    assert created["host"] == "203.0.113.10"
    assert created["app"] == "billing"
    assert created["version"] == "0.38.34"
    assert created["actions"] == ["create"]
    first_call = data(state)["calls"][0]
    assert "dokku@203.0.113.10" in first_call
    assert "StrictHostKeyChecking=no" not in first_call
    assert "accept-new" not in first_call
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert data(state)["apps"] == ["billing"]
    assert remote_commands(state)[-2:] == [["version"], ["apps:exists", "billing"]]
    reused = public_result(second)
    assert reused["host"] == "203.0.113.10"
    assert reused["app"] == "billing"
    assert reused["actions"] == []


@pytest.mark.parametrize(
    "extra",
    [
        {"version": "0.33.9"},
        {"version": "0.38.35"},
        {"version": "0.39.0"},
        {"version_raw": "v0.38.34\n"},
    ],
)
def test_unsupported_version_is_rejected_without_mutation(dokku, extra):
    run, state = dokku
    state.write_text(json.dumps({"apps": ["billing"], **extra}))
    result = run()
    assert result.returncode != 0, result.stdout
    assert "not upgraded" in result.stdout
    assert data(state)["apps"] == ["billing"]
    assert remote_commands(state) == [["version"]]


def test_oldest_supported_version_reuses_existing_app(dokku):
    run, state = dokku
    state.write_text(json.dumps({"apps": ["billing"], "version": "0.34.0"}))
    result = run()
    assert result.returncode == 0, result.stdout
    assert changed(result) == 0
    assert public_result(result)["version"] == "0.34.0"
    assert public_result(result)["actions"] == []


def test_ssh_failure_does_not_mutate_or_leak(dokku):
    run, state = dokku
    state.write_text(json.dumps(data(state) | {"fail": "ssh"}))
    result = run(verbose=True)
    assert result.returncode != 0
    assert "do-not-leak-test-secret" not in result.stdout
    assert data(state)["apps"] == []
    assert all(command[0] != "apps:create" for command in remote_commands(state))


@pytest.mark.parametrize("present,expected_changed", [(False, 1), (True, 0)])
def test_check_mode_predicts_creation_without_mutation(
    dokku, present, expected_changed
):
    run, state = dokku
    apps = ["billing"] if present else []
    state.write_text(json.dumps({"apps": apps, "version": "0.38.34"}))
    result = run(check=True)
    assert result.returncode == 0, result.stdout
    assert changed(result) == expected_changed
    assert data(state)["apps"] == apps
    assert all(command[0] != "apps:create" for command in remote_commands(state))
    assert remote_commands(state)[0] == ["version"]
    body = public_result(result)
    assert body["host"] == "203.0.113.10"
    assert body["app"] == "billing"
    if present:
        assert body["actions"] == []
        assert body["exists"] is True
        assert body["planned"] is False
    else:
        assert body["actions"] == ["create"]
        assert body["exists"] is False
        assert body["planned"] is True


def test_create_failure_keeps_completed_app_for_rerun(dokku):
    run, state = dokku
    state.write_text(
        json.dumps(data(state) | {"fail": "create", "record_partial": True})
    )
    failed = run(verbose=True)
    assert failed.returncode != 0
    assert "do-not-leak-test-secret" not in failed.stdout
    assert "is present" in failed.stdout
    assert "rollback" in failed.stdout
    assert data(state)["apps"] == ["billing"]
    assert [command[0] for command in remote_commands(state)] == [
        "version",
        "apps:exists",
        "apps:create",
        "apps:exists",
    ]
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert [command[0] for command in remote_commands(state)].count("apps:create") == 1
    assert public_result(second)["actions"] == []


def test_create_failure_without_an_app_reports_it_absent(dokku):
    run, state = dokku
    state.write_text(json.dumps(data(state) | {"fail": "create"}))
    result = run()
    assert result.returncode != 0
    assert "is absent" in result.stdout
    assert "was kept" not in result.stdout
    assert data(state)["apps"] == []
    assert [command[0] for command in remote_commands(state)][-2:] == [
        "apps:create",
        "apps:exists",
    ]


def test_missing_private_key_fails_before_ssh(dokku, tmp_path):
    run, state = dokku
    result = run({"dokku_ssh_private_key": str(tmp_path / "missing")})
    assert result.returncode != 0
    assert not data(state).get("calls")


def test_caller_ssh_configuration_is_forwarded(dokku, tmp_path):
    run, state = dokku
    key = tmp_path / "id"
    key.write_text("private-key-marker\n")
    known = tmp_path / "known_hosts"
    known.write_text("203.0.113.10 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake\n")
    config = tmp_path / "ssh_config"
    config.write_text("Host *\n")
    result = run(
        {
            "dokku_ssh_port": 2222,
            "dokku_ssh_private_key": str(key),
            "dokku_ssh_known_hosts": str(known),
            "dokku_ssh_config": str(config),
        },
        verbose=True,
    )
    assert result.returncode == 0, result.stdout
    assert "private-key-marker" not in result.stdout
    call = data(state)["calls"][0]
    assert call[call.index("-p") + 1] == "2222"
    assert call[call.index("-i") + 1] == str(key)
    assert "IdentitiesOnly=yes" in call
    assert "UserKnownHostsFile=" + str(known) in call
    assert "GlobalKnownHostsFile=/dev/null" in call
    assert call[call.index("-F") + 1] == str(config)
    assert "dokku@203.0.113.10" in call
    assert "BatchMode=yes" in call
    assert "StrictHostKeyChecking=no" not in call
    assert "accept-new" not in call
    assert "ssh-keys:add" not in call


def test_example_playbook_runs_the_public_role(dokku, installed, tmp_path):
    run, state = dokku
    varfile = tmp_path / "vars.json"
    varfile.write_text(json.dumps(run.variables))
    playbook = installed / "ansible_collections/madebyphunky/dokku/playbooks/app.yml"
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            str(playbook),
            "-e",
            f"@{varfile}",
        ],
        env=run.env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert data(state)["apps"] == ["billing"]
    assert remote_commands(state) == [
        ["version"],
        ["apps:exists", "billing"],
        ["apps:create", "billing"],
    ]


@pytest.mark.parametrize(
    "port_override,expected_port", [(None, "2222"), (2200, "2200")]
)
def test_ssh_config_port_is_used_unless_explicitly_overridden(
    dokku, tmp_path, port_override, expected_port
):
    run, state = dokku
    config = tmp_path / "ssh_config"
    config.write_text("Host *\n    Port 2222\n")
    overrides = {"dokku_ssh_config": str(config)}
    if port_override is not None:
        overrides["dokku_ssh_port"] = port_override
    result = run(overrides)
    assert result.returncode == 0, result.stdout
    call = data(state)["calls"][0]
    destination = next(i for i, arg in enumerate(call) if arg.startswith("dokku@"))
    resolved = subprocess.run(
        ["ssh", "-G", *call[: destination + 1]],
        text=True,
        capture_output=True,
        check=True,
    )
    assert f"port {expected_port}" in resolved.stdout.splitlines()
