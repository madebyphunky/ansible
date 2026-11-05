"""Installed creation-only Role contract; never contacts Hetzner."""

import json
import os
import shutil

import pytest

from conftest import ROOT
from runner import changed, invoke


@pytest.fixture
def hetzner(installed, tmp_path):
    modules = installed / "ansible_collections/hetzner/hcloud/plugins/modules"
    modules.mkdir(parents=True, exist_ok=True)
    for name in ("server", "server_info"):
        shutil.copyfile(ROOT / "tests/fixtures/hetzner.py", modules / f"{name}.py")
    state = tmp_path / "hetzner.json"
    env = os.environ.copy()
    env.update(
        ANSIBLE_COLLECTIONS_PATH=str(installed),
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_PYTHON_INTERPRETER=os.sys.executable,
        HETZNER_TEST_STATE=str(state),
        HCLOUD_TOKEN="secret-environment-token",
    )
    variables = dict(
        hetzner_server_api_token="secret-explicit-token",
        hetzner_server_name="example-web-01",
        hetzner_server_image="ubuntu-24.04",
        hetzner_server_type="cx23",
        hetzner_server_location="nbg1",
        hetzner_server_ssh_keys=["existing-key"],
    )

    def run(overrides=None, scenario="success", **kwargs):
        return invoke(
            variables | (overrides or {}),
            role="madebyphunky.hetzner.server",
            env=env | {"HETZNER_TEST_SCENARIO": scenario},
            **kwargs,
        )

    def calls():
        return json.loads(state.read_text())["calls"] if state.exists() else []

    return run, calls, variables


def test_creation_returns_running_identity_and_addresses(hetzner):
    run, calls, _ = hetzner
    result = run(
        {"hetzner_server_firewall": "existing-firewall"},
        tasks_after=[
            {
                "ansible.builtin.assert": {
                    "that": [
                        "hetzner_server_result.id | int == 12345",
                        "hetzner_server_result.ipv4 == '192.0.2.10'",
                        "hetzner_server_result.ipv6 == '2001:db8::/64'",
                        "hetzner_server_result.status == 'running'",
                    ]
                }
            }
        ],
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert [call["operation"] for call in calls()] == ["info", "create"]
    creation = calls()[1]
    assert creation["firewalls"] == ["existing-firewall"]
    assert creation["ssh_keys"] == ["existing-key"]
    assert creation["enable_ipv4"] is True
    assert creation["enable_ipv6"] is True
    assert creation["state"] == "started"


@pytest.mark.parametrize(
    "overrides",
    [
        {"hetzner_server_name": ""},
        {"hetzner_server_image": " "},
        {"hetzner_server_type": ""},
        {"hetzner_server_location": ""},
        {"hetzner_server_ssh_keys": []},
        {"hetzner_server_ssh_keys": [""]},
        {"hetzner_server_firewall": ""},
        {"hetzner_server_api_token": ""},
        {"hetzner_server_id": "12345"},
        {"hetzner_server_id": ""},
    ],
)
def test_invalid_inputs_never_contact_provider(hetzner, overrides):
    run, calls, _ = hetzner
    result = run(overrides)
    assert result.returncode != 0, result.stdout
    assert calls() == []


def test_required_argument_validation(hetzner):
    run, calls, variables = hetzner
    del variables["hetzner_server_image"]
    result = run()
    assert result.returncode != 0
    assert calls() == []


def test_name_collision_never_calls_mutating_module(hetzner):
    run, calls, _ = hetzner
    result = run(scenario="collision")
    assert result.returncode != 0
    assert all(call["operation"] == "info" for call in calls())
    assert "12345" in result.stdout


def test_check_mode_predicts_without_identity(hetzner):
    run, calls, _ = hetzner
    result = run(
        check=True,
        tasks_after=[
            {"ansible.builtin.assert": {"that": ["hetzner_server_result == {}"]}}
        ],
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert [call["operation"] for call in calls()] == ["info", "create"]


def test_partial_failure_recovers_id_and_redacts_provider_output(hetzner):
    run, calls, _ = hetzner
    result = run(scenario="partial_failure", verbose=True)
    assert result.returncode != 0
    assert "12345" in result.stdout
    assert "No resources were deleted" in result.stdout
    assert "secret-explicit-token" not in result.stdout
    assert "secret-environment-token" not in result.stdout
    assert [call["operation"] for call in calls()] == ["info", "create", "info"]


def test_lookup_failure_never_creates(hetzner):
    run, calls, _ = hetzner
    result = run(scenario="lookup_failure", verbose=True)
    assert result.returncode != 0
    assert "secret-explicit-token" not in result.stdout
    assert all(call["operation"] == "info" for call in calls())


def test_provider_must_report_running(hetzner):
    run, _, _ = hetzner
    result = run(scenario="stopped")
    assert result.returncode != 0
    assert "12345" in result.stdout


def test_environment_fallback_and_disabled_public_addresses(hetzner):
    run, _, variables = hetzner
    del variables["hetzner_server_api_token"]
    result = run(
        {"hetzner_server_enable_ipv4": False, "hetzner_server_enable_ipv6": False},
        tasks_after=[
            {
                "ansible.builtin.assert": {
                    "that": [
                        "hetzner_server_result.ipv4 == None",
                        "hetzner_server_result.ipv6 == None",
                    ]
                }
            }
        ],
    )
    assert result.returncode == 0, result.stdout
