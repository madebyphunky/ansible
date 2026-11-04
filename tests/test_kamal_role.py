"""Contracts run the installed public Role against an isolated Kamal CLI."""

import json
import os
from pathlib import Path

import pytest
import yaml

from runner import changed, invoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def kamal(installed, tmp_path):
    executable = tmp_path / "kamal"
    executable.write_text((ROOT / "tests/fixtures/kamal_cli.py").read_text())
    executable.chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"hosts": ["missing", "ready"]}))
    variables = {
        "kamal_workdir": str(tmp_path),
        "kamal_executable": str(executable),
        "kamal_config": {
            "service": "example",
            "image": "example/app",
            "servers": {"web": ["192.0.2.1"]},
            "registry": {"server": "registry.example.com", "username": "example"},
        },
        "kamal_environment": {"KAMAL_TEST_STATE": str(state)},
    }
    env = os.environ | {
        "ANSIBLE_COLLECTIONS_PATH": str(installed),
        "ANSIBLE_NOCOLOR": "1",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_PYTHON_INTERPRETER": os.sys.executable,
    }

    def run(overrides=None, **kwargs):
        return invoke(
            variables | (overrides or {}),
            env=env,
            role="madebyphunky.kamal.setup",
            **kwargs
        )

    return run, state, variables, tmp_path


def data(state):
    return json.loads(state.read_text())


def assert_clean(state):
    assert all(
        not Path(p).exists()
        for p in data(state).get("paths", [])
        if Path(p).name.startswith("ansible-kamal-")
    )


def test_bootstrap_missing_hosts_then_noop(kamal):
    run, state, _, _ = kamal
    first = run()
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert data(state)["hosts"] == ["ready", "ready"]
    assert len(data(state)["calls"]) == 3
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0
    assert len(data(state)["calls"]) == 4
    assert_clean(state)


def test_existing_config_is_unchanged_and_destination_passed(kamal):
    run, state, variables, directory = kamal
    config = directory / "deploy.yml"
    config.write_text(yaml.safe_dump(variables.pop("kamal_config")))
    before = config.read_bytes()
    result = run({"kamal_config_file": "deploy.yml", "kamal_destination": "staging"})
    assert result.returncode == 0, result.stdout
    assert config.read_bytes() == before
    assert all(
        "--destination" in call and "staging" in call for call in data(state)["calls"]
    )


@pytest.mark.parametrize("hosts,expected", [(["missing"], 1), (["ready"], 0)])
def test_check_mode_only_inspects(kamal, hosts, expected):
    run, state, _, _ = kamal
    state.write_text(json.dumps({"hosts": hosts}))
    result = run(check=True)
    assert result.returncode == 0, result.stdout
    assert changed(result) == expected
    assert data(state)["hosts"] == hosts
    assert len(data(state)["calls"]) == 1
    assert_clean(state)


@pytest.mark.parametrize(
    "extra",
    [
        {"hosts": ["broken"]},
        {"fail": True},
        {"invalid_output": True},
        {"empty_output": True},
    ],
)
def test_inspection_failure_never_bootstraps_and_redacts(kamal, extra):
    run, state, _, _ = kamal
    state.write_text(json.dumps(data(state) | extra))
    result = run(verbose=True)
    assert result.returncode != 0
    assert "do-not-leak-test-secret" not in result.stdout
    assert len(data(state)["calls"]) == 1
    assert_clean(state)


def test_bootstrap_must_establish_ready_state(kamal):
    run, state, _, _ = kamal
    state.write_text(json.dumps(data(state) | {"ineffective": True}))
    result = run()
    assert result.returncode != 0
    assert "still absent" in result.stdout
    assert_clean(state)


def test_conflicting_inputs_fail_before_cli(kamal):
    run, state, _, _ = kamal
    result = run({"kamal_config_file": "deploy.yml"})
    assert result.returncode != 0
    assert not data(state).get("calls")


def test_missing_inputs_fail_before_cli(kamal):
    run, state, variables, _ = kamal
    variables.pop("kamal_config")
    result = run()
    assert result.returncode != 0
    assert not data(state).get("calls")


def test_config_and_environment_are_redacted(kamal):
    run, _, variables, _ = kamal
    variables["kamal_config"]["registry"]["password"] = "private-config-marker"
    variables["kamal_environment"]["SECRET_TEST"] = "private-environment-marker"
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert "private-config-marker" not in result.stdout
    assert "private-environment-marker" not in result.stdout


@pytest.mark.parametrize(
    "provider,check",
    [
        ("", False),
        ("gandi", False),
        ("gandi", True),
        ("invalid", False),
        ("gandi-failure", False),
    ],
)
def test_optional_dns_composer(kamal, installed, provider, check):
    import subprocess

    run, state, variables, directory = kamal
    dns_state = directory / "dns-state.json"
    variables = variables | {
        "application_kamal_dns_provider": (
            "gandi" if provider == "gandi-failure" else provider
        ),
        "gandi_livedns_zone": "example.com",
        "gandi_livedns_personal_access_token": "dummy-variable-token",
        "gandi_livedns_records": [
            {
                "name": "fail" if provider == "gandi-failure" else "app",
                "type": "A",
                "ttl": 300,
                "values": ["192.0.2.10"],
            }
        ],
    }
    varfile = directory / "vars.json"
    varfile.write_text(json.dumps(variables))
    env = os.environ | {
        "ANSIBLE_COLLECTIONS_PATH": str(installed),
        "ANSIBLE_NOCOLOR": "1",
        "ANSIBLE_PYTHON_INTERPRETER": os.sys.executable,
        "INFRA_TEST_STATE": str(dns_state),
    }
    command = [
        "ansible-playbook",
        "-i",
        "localhost,",
        "-c",
        "local",
        str(
            installed
            / "ansible_collections/madebyphunky/application/playbooks/kamal_setup.yml"
        ),
        "-e",
        "@" + str(varfile),
    ]
    if check:
        command.append("--check")
    result = subprocess.run(
        command, env=env, text=True, capture_output=True, timeout=120
    )
    if provider in ("invalid", "gandi-failure"):
        assert result.returncode != 0
        assert not data(state).get("calls")
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert data(state)["calls"]
        if provider == "gandi":
            assert dns_state.exists()
            records = json.loads(dns_state.read_text())["records"]
            assert bool(records) is not check
        else:
            assert not dns_state.exists()
    assert_clean(state)


def test_bootstrap_failure_cleans_temporary_configuration(kamal):
    run, state, _, _ = kamal
    state.write_text(json.dumps(data(state) | {"fail_bootstrap": True}))
    result = run()
    assert result.returncode != 0
    assert "server bootstrap failed" in result.stdout
    assert "do-not-leak-test-secret" not in result.stdout
    assert len(data(state)["calls"]) == 2
    assert_clean(state)
