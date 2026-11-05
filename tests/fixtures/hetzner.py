"""Read-only lookup and creation double for the official Hetzner modules."""

import json
import os
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule


def main():
    info = Path(__file__).stem == "server_info"
    spec = dict(api_token=dict(type="str", no_log=True), name=dict(type="str"))
    if not info:
        spec.update(
            image=dict(type="str"),
            server_type=dict(type="str"),
            location=dict(type="str"),
            ssh_keys=dict(type="list", elements="str"),
            firewalls=dict(type="list", elements="str"),
            enable_ipv4=dict(type="bool"),
            enable_ipv6=dict(type="bool"),
            state=dict(type="str"),
        )
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    path = Path(os.environ["HETZNER_TEST_STATE"])
    data = json.loads(path.read_text()) if path.exists() else {"calls": []}
    params = {k: v for k, v in module.params.items() if k != "api_token"}
    data["calls"].append(dict(operation="info" if info else "create", **params))
    scenario = os.environ.get("HETZNER_TEST_SCENARIO", "success")
    server = dict(
        id=12345, ipv4_address="192.0.2.10", ipv6="2001:db8::/64", status="running"
    )
    if not info and not module.check_mode:
        data["server"] = server
    path.write_text(json.dumps(data))
    if info:
        if scenario == "lookup_failure":
            module.fail_json(msg="provider error " + module.params["api_token"])
        module.exit_json(
            hcloud_server_info=(
                [server] if scenario == "collision" or data.get("server") else []
            )
        )
    if scenario == "partial_failure":
        module.fail_json(msg="sensitive provider error " + module.params["api_token"])
    if scenario == "stopped":
        server["status"] = "off"
    if not module.params["enable_ipv4"]:
        server["ipv4_address"] = None
    if not module.params["enable_ipv6"]:
        server["ipv6"] = None
    module.exit_json(
        changed=True, **({} if module.check_mode else {"hcloud_server": server})
    )


if __name__ == "__main__":
    main()
