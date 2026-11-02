"""Live acceptance checks for Molecule; persists exact identities, never credentials."""

import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from runner import changed, invoke


def read_record(zone, name):
    token = os.environ["GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN"]
    url = "https://api.gandi.net/v5/livedns/domains/{}/records/{}/A".format(
        quote(zone, safe=""), quote(name, safe="")
    )
    request = Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(
            "LiveDNS read failed with HTTP status " + str(error.code)
        ) from None


def content(record):
    return (
        None
        if record is None
        else (record["rrset_ttl"], sorted(record["rrset_values"]))
    )


def run(manifest, records, *, check=False, expect_failure=False, expected_changes=None):
    result = invoke(
        {
            "gandi_livedns_zone": manifest["gandi_livedns_zone"],
            "gandi_livedns_records": records,
        },
        check=check,
    )
    assert (
        os.environ["GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN"] not in result.stdout
    ), "Credential leaked"
    if expect_failure:
        assert result.returncode != 0, "Invalid input unexpectedly succeeded"
    else:
        assert result.returncode == 0, result.stdout
        if expected_changes is not None:
            assert changed(result) == expected_changes, result.stdout


def cleanup_records(manifest, names):
    # Delete one at a time so a failure does not prevent attempts on other owned identities.
    failures = []
    for name in names:
        try:
            run(manifest, [{"name": name, "type": "A", "state": "absent"}])
            assert read_record(manifest["gandi_livedns_zone"], name) is None
        except Exception as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError(
            "Cleanup incomplete; retain manifest and retry: " + "\n".join(failures)
        )


def prepare(path):
    if path.exists():
        raise RuntimeError(
            "Run manifest already exists; clean it up before starting another run"
        )
    zone = os.environ.get("GANDI_LIVEDNS_TEST_ZONE", "")
    if not zone or not os.environ.get("GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN"):
        raise RuntimeError(
            "Set the dedicated test zone and PAT before running live tests"
        )
    suffix = os.environ.get("GANDI_LIVEDNS_TEST_NAME_SUFFIX", "")
    prefix = "gandi-test-" + uuid.uuid4().hex
    names = {
        key: prefix + "-" + key + ("." + suffix if suffix else "")
        for key in ("managed", "omitted", "sentinel", "failure")
    }
    for name in names.values():
        assert (
            read_record(zone, name) is None
        ), "Allocated identity already exists; refusing ownership"
    record = lambda name: {
        "name": name,
        "type": "A",
        "ttl": 300,
        "values": ["192.0.2.10"],
    }
    manifest = {
        "gandi_livedns_zone": zone,
        "names": names,
        "owned": list(names.values()),
        "gandi_livedns_records": [record(names["managed"]), record(names["omitted"])],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Record every exact identity before creating any records so failed setup is cleanable.
    path.write_text(json.dumps(manifest))
    run(manifest, [record(names["sentinel"])], expected_changes=1)


def verify(manifest):
    zone, names = manifest["gandi_livedns_zone"], manifest["names"]
    snapshot = lambda: {
        key: content(read_record(zone, name)) for key, name in names.items()
    }
    before = snapshot()
    for key in ("managed", "omitted", "sentinel"):
        assert before[key] == (300, ["192.0.2.10"]), "Creation did not converge"
    run(manifest, manifest["gandi_livedns_records"], expected_changes=0)
    updated = {
        "name": names["managed"],
        "type": "A",
        "ttl": 600,
        "values": ["192.0.2.20", "192.0.2.21"],
    }
    run(manifest, [updated], check=True, expected_changes=1)
    assert snapshot() == before, "Check mode mutated DNS"
    run(manifest, [updated], expected_changes=1)
    assert content(read_record(zone, names["managed"])) == (600, updated["values"])
    run(manifest, [updated], expected_changes=0)
    assert content(read_record(zone, names["omitted"])) == before["omitted"]
    assert content(read_record(zone, names["sentinel"])) == before["sentinel"]
    checkpoint = snapshot()
    would_change = dict(updated, ttl=900)
    invalid = {"name": names["failure"], "type": "A", "values": ["192.0.2.99"]}
    run(manifest, [would_change, invalid], expect_failure=True)
    assert snapshot() == checkpoint, "Invalid batch changed DNS"
    # An injected test failure must still clean up its exact fixture while preserving other records.
    try:
        run(manifest, [dict(updated, name=names["failure"])], expected_changes=1)
        raise InterruptedError("Intentional acceptance-test failure")
    except InterruptedError:
        pass
    finally:
        cleanup_records(manifest, [names["failure"]])
    assert snapshot() == checkpoint, "Failure cleanup altered unrelated records"
    run(
        manifest,
        [{"name": names["managed"], "type": "A", "state": "absent"}],
        expected_changes=1,
    )
    assert read_record(zone, names["managed"]) is None
    run(
        manifest,
        [{"name": names["managed"], "type": "A", "state": "absent"}],
        expected_changes=0,
    )
    assert content(read_record(zone, names["omitted"])) == before["omitted"]
    assert content(read_record(zone, names["sentinel"])) == before["sentinel"]
    print(
        "Live creation, replacement, idempotency, check mode, validation, deletion, and preservation passed"
    )


def main():
    action, path = sys.argv[1], Path(sys.argv[2])
    if action == "prepare":
        prepare(path)
    elif action == "cleanup":
        if path.exists():
            manifest = json.loads(path.read_text())
            cleanup_records(manifest, manifest["owned"])
            path.unlink()
    elif action == "verify":
        verify(json.loads(path.read_text()))
    else:
        raise RuntimeError("Unknown live action")


if __name__ == "__main__":
    main()
