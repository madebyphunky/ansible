#!/usr/bin/python
# Copyright: (c) 2026, madebyphunky
# SPDX-License-Identifier: MIT

"""Supporting module for the Spaceship DNS Role."""

DOCUMENTATION = r"""
---
module: dns_records
short_description: Reconcile explicitly owned Spaceship DNS record sets
version_added: "0.1.0"
author: madebyphunky
description:
  - Reconciles complete explicitly declared record sets without pruning omitted sets.
  - Validates every declaration before reading or mutating the provider.
  - Stops on the first failure, retaining completed changes without rollback.
requirements:
  - dnspython >= 2.7
options:
  zone:
    description: Existing Spaceship DNS zone without a trailing dot.
    required: true
    type: str
  records:
    description: Nonempty list of name, type, state, ttl and string values declarations.
    required: true
    type: raw
  api_key:
    description: Spaceship API key with DNS read and write scopes.
    required: true
    type: str
  api_secret:
    description: Corresponding Spaceship API secret.
    required: true
    type: str
attributes:
  check_mode:
    support: full
  diff_mode:
    support: none
"""
EXAMPLES = r"""
- name: Declare an address record
  madebyphunky.spaceship.dns_records:
    zone: example.com
    api_key: "{{ spaceship_dns_api_key }}"
    api_secret: "{{ spaceship_dns_api_secret }}"
    records:
      - name: www
        type: A
        ttl: 300
        values: [192.0.2.1]
"""
RETURN = r"""
changed:
  description: Whether any explicitly owned record set needs changes.
  type: bool
  returned: always
"""

import json

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible.module_utils.urls import fetch_url

try:
    from ansible_collections.madebyphunky.spaceship.plugins.module_utils.dns_records import (
        reconcile,
        validate,
    )

    HAS_DNS = True
except ImportError:
    HAS_DNS = False


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone=dict(type="str", required=True),
            records=dict(type="raw", required=True),
            api_key=dict(type="str", required=True, no_log=True),
            api_secret=dict(type="str", required=True, no_log=True),
        ),
        supports_check_mode=True,
    )
    if not HAS_DNS:
        module.fail_json(msg=missing_required_lib("dnspython >= 2.7"))
    for field in ("api_key", "api_secret"):
        if not module.params[field].strip():
            module.fail_json(msg="Supply nonblank Spaceship API key and secret")
    try:
        declarations = validate(module.params["zone"], module.params["records"])
    except Exception as exc:
        module.fail_json(msg=f"Invalid DNS declarations: {exc}")
    url = "https://spaceship.dev/api/v1/dns/records/" + module.params["zone"].lower()
    headers = {
        "X-API-Key": module.params["api_key"],
        "X-API-Secret": module.params["api_secret"],
        "Content-Type": "application/json",
    }
    module.params["follow_redirects"] = "none"
    mutated = False

    def request(method, query, body):
        nonlocal mutated
        response, info = fetch_url(
            module,
            url + query,
            method=method,
            headers=headers,
            data=json.dumps(body) if body is not None else None,
            timeout=30,
            use_netrc=False,
            unredirected_headers=["X-API-Key", "X-API-Secret"],
        )
        expected = 200 if method == "GET" else 204
        if info["status"] != expected:
            # Never include provider response bodies or headers in errors.
            module.fail_json(
                msg=f'Spaceship DNS {method} failed (HTTP {info["status"]}); rerun to converge',
                changed=mutated,
            )
        if method != "GET":
            mutated = True
        return json.loads(response.read()) if method == "GET" else None

    try:
        changed = reconcile(declarations, request, module.check_mode)
    except Exception as exc:
        module.fail_json(
            msg=f"Spaceship DNS reconciliation failed: {exc}", changed=mutated
        )
    module.exit_json(changed=changed)


if __name__ == "__main__":
    main()
