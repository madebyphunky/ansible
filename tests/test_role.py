import copy
import json
import subprocess
from pathlib import Path

import pytest

from runner import changed


def test_converge_replace_omit_delete_and_check_mode(contract):
    run, variables, _, data = contract
    first = run()
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert changed(run()) == 0
    record = variables["gandi_livedns_records"][0]
    updated = dict(record, ttl=600, values=["192.0.2.2", "192.0.2.3"])
    preview = run({"gandi_livedns_records": [updated]}, check=True)
    assert preview.returncode == 0, preview.stdout
    assert changed(preview) == 1
    assert data()["records"]["example.com/www/a"]["ttl"] == 300
    assert changed(run({"gandi_livedns_records": [updated]})) == 1
    assert data()["records"]["example.com/www/a"] == {
        "ttl": 600,
        "values": updated["values"],
    }
    unrelated = dict(record, name="sentinel")
    assert run({"gandi_livedns_records": [unrelated]}).returncode == 0
    assert data()["records"]["example.com/www/a"]["ttl"] == 600
    # Even if supplied on an absent entry, values must not cause partial-value deletion.
    deletion = dict(updated, state="absent")
    assert run({"gandi_livedns_records": [deletion]}).returncode == 0
    assert "example.com/www/a" not in data()["records"]
    assert "example.com/sentinel/a" in data()["records"]
    assert data()["calls"][-1]["values"] is None
    assert changed(run({"gandi_livedns_records": [deletion]})) == 0


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "www", "type": "A", "values": ["192.0.2.1"]},
        {"name": "www", "type": "A", "ttl": 300},
        {"name": "www", "type": "A", "ttl": 300, "values": []},
        {"name": "www", "type": "A", "ttl": 300, "values": [42]},
        {"name": "www", "type": "A", "ttl": "300", "values": ["192.0.2.1"]},
        {"name": "www", "type": "a", "state": "absent"},
        {"name": "www", "type": "A", "state": "invalid"},
        {"type": "A", "state": "absent"},
        {"name": "", "type": "A", "state": "absent"},
        {"name": "www.example.com", "type": "A", "state": "absent"},
        {"name": "www.", "type": "A", "state": "absent"},
        {"name": "../www", "type": "A", "state": "absent"},
        {"name": "www", "type": "A", "state": "absent", "typo": True},
    ],
)
def test_invalid_batch_never_reaches_provider(contract, entry):
    run, variables, _, data = contract
    records = variables["gandi_livedns_records"] + [entry]
    result = run({"gandi_livedns_records": records})
    assert result.returncode != 0
    assert data()["calls"] == []


@pytest.mark.parametrize(
    "kind", ["missing", "empty", "duplicate", "case-alias", "no-zone"]
)
def test_invalid_top_level_or_duplicate_input(contract, kind):
    run, variables, _, data = contract
    if kind == "missing":
        variables.pop("gandi_livedns_records")
    elif kind == "empty":
        variables["gandi_livedns_records"] = []
    elif kind in ("duplicate", "case-alias"):
        duplicate = copy.deepcopy(variables["gandi_livedns_records"][0])
        if kind == "case-alias":
            duplicate["name"] = "WWW"
        variables["gandi_livedns_records"].append(duplicate)
    else:
        variables.pop("gandi_livedns_zone")
    result = run()
    assert result.returncode != 0
    assert data()["calls"] == []


@pytest.mark.parametrize("name", ["@", "*.preview", "_acme-challenge", "nested.www"])
def test_relative_identity_forms(contract, name):
    run, variables, _, _ = contract
    variables["gandi_livedns_records"][0]["name"] = name
    result = run()
    assert result.returncode == 0, result.stdout


def test_auth_precedence_fallback_missing_and_redaction(contract):
    run, variables, env, data = contract
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert "dummy-variable-token" not in result.stdout
    assert "dummy-environment-token" not in result.stdout
    variables.pop("gandi_livedns_personal_access_token")
    env["INFRA_TEST_TOKEN"] = "dummy-environment-token"
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert "dummy-environment-token" not in result.stdout
    before = len(data()["calls"])
    env.pop("GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN")
    result = run()
    assert result.returncode != 0
    assert len(data()["calls"]) == before


def test_stop_on_failure_retains_completed_changes_and_redacts(contract):
    run, variables, _, data = contract
    record = variables["gandi_livedns_records"][0]
    variables["gandi_livedns_records"] = [
        record,
        dict(record, name="fail"),
        dict(record, name="never"),
    ]
    result = run(verbose=True)
    assert result.returncode != 0
    assert "dummy-variable-token" not in result.stdout
    assert list(data()["records"]) == ["example.com/www/a"]
    assert [call["key"] for call in data()["calls"]] == [
        "example.com/www/a",
        "example.com/fail/a",
    ]


def test_installed_example_syntax_and_safe_default(installed, contract, tmp_path):
    _, variables, env, data = contract
    playbook = (
        installed
        / "ansible_collections/madebyphunky/infra/playbooks/dns_gandi_livedns.yml"
    )
    result = subprocess.run(
        ["ansible-playbook", str(playbook), "--syntax-check"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps(variables))
    result = subprocess.run(
        [
            "ansible-playbook",
            str(playbook),
            "-i",
            "localhost,other,",
            "-c",
            "local",
            "-e",
            "@" + str(inputs),
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert changed(result) == 1
    assert "other" not in result.stdout
    assert len(data()["calls"]) == 1


def test_explicit_blank_token_does_not_fall_back(contract):
    run, variables, _, data = contract
    variables["gandi_livedns_personal_access_token"] = ""
    result = run()
    assert result.returncode != 0
    assert data()["calls"] == []


def test_values_pass_through_without_requoting_or_expansion(contract):
    run, variables, _, data = contract
    record = {
        "name": "txt",
        "type": "TXT",
        "ttl": 300,
        "values": [
            '"v=spf1 include:example.net ~all"',
            '"unchanged \\"quoted\\" text"',
        ],
    }
    variables["gandi_livedns_records"] = [record]
    result = run()
    assert result.returncode == 0, result.stdout
    assert data()["records"]["example.com/txt/txt"]["values"] == record["values"]
