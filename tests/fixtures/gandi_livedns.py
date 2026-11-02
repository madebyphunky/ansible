#!/usr/bin/python
"""Offline provider double: stores RRsets, observes calls, and supports injected failure."""

import json
import os
from pathlib import Path
from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            record=dict(type="str", required=True),
            type=dict(type="str", required=True),
            state=dict(type="str", default="present"),
            ttl=dict(type="int"),
            values=dict(type="list", elements="str"),
            personal_access_token=dict(type="str", no_log=True),
        ),
        supports_check_mode=True,
    )
    path = Path(os.environ["INFRA_TEST_STATE"])
    data = (
        json.loads(path.read_text()) if path.exists() else {"records": {}, "calls": []}
    )
    params = module.params
    key = "/".join(params[k].lower() for k in ("domain", "record", "type"))
    data["calls"].append(
        {"key": key, "state": params["state"], "values": params["values"]}
    )
    path.write_text(json.dumps(data))
    if params["personal_access_token"] != os.environ.get(
        "INFRA_TEST_TOKEN", "dummy-variable-token"
    ):
        module.fail_json(msg="Unexpected credential selected")
    if params["record"] == "fail":
        module.fail_json(msg="Injected provider failure")
    before = data["records"].get(key)
    desired = (
        {"ttl": params["ttl"], "values": params["values"]}
        if params["state"] == "present"
        else None
    )
    changed = before != desired
    if not module.check_mode:
        if desired is None:
            data["records"].pop(key, None)
        else:
            data["records"][key] = desired
        path.write_text(json.dumps(data))
    module.exit_json(changed=changed)


if __name__ == "__main__":
    main()
