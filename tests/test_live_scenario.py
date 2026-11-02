"""Exercise the acceptance harness against the isolated provider, never real DNS."""

import json

import live_acceptance as live


def test_live_lifecycle_and_failure_cleanup_offline(contract, monkeypatch, tmp_path):
    _, _, env, data = contract
    env["INFRA_TEST_TOKEN"] = "dummy-environment-token"
    env["GANDI_LIVEDNS_TEST_ZONE"] = "example.com"
    env["GANDI_LIVEDNS_TEST_NAME_SUFFIX"] = "xyz"
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def read_record(zone, name):
        record = data()["records"].get(f"{zone}/{name}/a")
        if record is None:
            return None
        return {"rrset_ttl": record["ttl"], "rrset_values": record["values"]}

    monkeypatch.setattr(live, "read_record", read_record)
    path = tmp_path / "dns-run.json"
    live.prepare(path)
    manifest = json.loads(path.read_text())
    assert all(name.endswith(".xyz") for name in manifest["owned"])
    assert "dummy-environment-token" not in path.read_text()
    live.run(manifest, manifest["gandi_livedns_records"], expected_changes=2)
    live.run(manifest, manifest["gandi_livedns_records"], expected_changes=0)
    live.verify(manifest)
    live.cleanup_records(manifest, manifest["owned"])
    assert data()["records"] == {}
