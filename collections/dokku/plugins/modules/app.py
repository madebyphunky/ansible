#!/usr/bin/python
# Copyright (c) 2026 madebyphunky
# SPDX-License-Identifier: MIT
"""Create or reuse one Dokku App over SSH without deploying source."""

from __future__ import annotations

import os
import re

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: app
short_description: Create or reuse one explicitly named Dokku App
description:
  - Runs on the controller and uses native Dokku commands over SSH as the dokku user.
  - Inspects the server version before mutation and does not upgrade the host.
options:
  host:
    type: str
    required: true
    description: Existing Dokku hostname or IP address.
  app:
    type: str
    required: true
    description: Explicit Dokku App name.
  port:
    type: int
    description: Optional SSH port override. Otherwise use the caller SSH configuration.
  private_key:
    type: path
    description: Existing private key path.
  known_hosts:
    type: path
    description: Caller-provided known hosts file.
  ssh_config:
    type: path
    description: Caller-provided OpenSSH configuration file.
  executable:
    type: str
    default: ssh
    description: SSH executable or wrapper.
author: madebyphunky
"""
EXAMPLES = r"""
- name: Create or reuse billing
  madebyphunky.dokku.app:
    host: 203.0.113.10
    app: billing
"""
RETURN = r"""
host:
  type: str
  returned: success
  description: Dokku host that was inspected.
app:
  type: str
  returned: success
  description: Dokku App name.
version:
  type: str
  returned: success
  description: Supported Dokku version reported by the host.
actions:
  type: list
  returned: success
  description: Mutations performed. Create is included when check mode would create.
exists:
  type: bool
  returned: success
  description: Whether the Dokku App exists after the run. False when check mode only predicts creation.
planned:
  type: bool
  returned: success
  description: Whether check mode predicts creation.
"""

APP_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
HOST_NAME = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
VERSION_LINE = re.compile(r"^dokku version (\d+\.\d+\.\d+)$")
# Command contract read from Dokku 0.34.0 and reference release 0.38.34.
# Live acceptance is pending.
MINIMUM_VERSION = (0, 34, 0)
MAXIMUM_VERSION = (0, 38, 34)
# Dokku exits 20 when apps:exists names a missing App. Other statuses are failures.
MISSING_APP = 20


class DokkuError(Exception):
    def __init__(self, message, **result):
        super().__init__(message)
        self.result = {"changed": False, **result}


def validate(params):
    host = params["host"]
    app = params["app"]
    port = params["port"]
    if not host or not HOST_NAME.fullmatch(host):
        raise DokkuError("dokku_host must be an explicit hostname or IP address.")
    if not app or not APP_NAME.fullmatch(app):
        raise DokkuError(
            "dokku_app must begin with a lowercase alphanumeric character and may "
            "only contain lowercase alphanumerics, dots, and hyphens."
        )
    if port is not None and (
        not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535
    ):
        raise DokkuError("dokku_ssh_port must be an integer from 1 to 65535.")
    for label, path in (
        ("dokku_ssh_private_key", params["private_key"]),
        ("dokku_ssh_known_hosts", params["known_hosts"]),
        ("dokku_ssh_config", params["ssh_config"]),
    ):
        if path is None:
            continue
        if (
            not path.startswith("/")
            or any(character.isspace() for character in path)
            or "," in path
        ):
            raise DokkuError(
                f"{label} must be an absolute path without spaces or commas."
            )
        if not os.path.isfile(path):
            raise DokkuError(f"{label} does not exist.")


def ssh_base(module, params):
    # BatchMode is always on the command line, so it beats dokku_ssh_config and
    # cannot wait for a prompt. Other caller SSH settings stay in that config.
    command = [
        module.get_bin_path(params["executable"], required=True),
        "-o",
        "BatchMode=yes",
    ]
    if params["port"] is not None:
        command += ["-p", str(params["port"])]
    if params["private_key"]:
        command += ["-i", params["private_key"], "-o", "IdentitiesOnly=yes"]
    if params["known_hosts"]:
        command += [
            "-o",
            "UserKnownHostsFile=" + params["known_hosts"],
            "-o",
            "GlobalKnownHostsFile=/dev/null",
        ]
    if params["ssh_config"]:
        command.append("-F")
        command.append(params["ssh_config"])
    command.append("dokku@" + params["host"])
    return command


def remote(module, base, arguments):
    # A list avoids a local shell. Remote stderr can contain secrets, so callers
    # keep only the exit status.
    rc, stdout, _stderr = module.run_command(base + arguments)
    return rc, stdout


def outcome(host, app, version, actions, exists, planned):
    return dict(
        changed=bool(actions),
        host=host,
        app=app,
        version=version,
        actions=actions,
        exists=exists,
        planned=planned,
    )


def supported_version(stdout):
    lines = [
        line.strip() for line in stdout.replace("\r", "").splitlines() if line.strip()
    ]
    if len(lines) != 1:
        return None
    match = VERSION_LINE.fullmatch(lines[0])
    if not match:
        return None
    parts = tuple(int(part) for part in match.group(1).split("."))
    if parts < MINIMUM_VERSION or parts > MAXIMUM_VERSION:
        return None
    return match.group(1)


def create_failure(module, base, host, app, version, create_rc):
    exists_rc, _stdout = remote(module, base, ["apps:exists", app])
    detail = {"host": host, "app": app, "version": version, "actions": []}
    if exists_rc == 0:
        raise DokkuError(
            f"Dokku apps:create failed (exit {create_rc}). The Dokku App is present "
            "and was kept; there is no automatic rollback. Rerun to reuse it.",
            changed=True,
            exists=True,
            **detail,
        )
    if exists_rc == MISSING_APP:
        raise DokkuError(
            f"Dokku apps:create failed (exit {create_rc}). The Dokku App is absent. "
            "The host was not otherwise changed.",
            changed=False,
            exists=False,
            **detail,
        )
    raise DokkuError(
        f"Dokku apps:create failed (exit {create_rc}). The Dokku App could not be "
        f"re-inspected (exit {exists_rc}). There is no automatic rollback.",
        changed=True,
        **detail,
    )


def ensure(module):
    params = module.params
    validate(params)
    host, app = params["host"], params["app"]
    base = ssh_base(module, params)
    version_rc, version_out = remote(module, base, ["version"])
    if version_rc != 0:
        raise DokkuError(
            f"Could not inspect the Dokku version over SSH (exit {version_rc}). "
            "The host was not changed."
        )
    version = supported_version(version_out)
    if version is None:
        raise DokkuError(
            "Dokku version is unsupported or unrecognized. Supported range is 0.34.0 "
            "through 0.38.34 (reference release 0.38.34). The host was not upgraded or changed."
        )
    exists_rc, _exists_out = remote(module, base, ["apps:exists", app])
    if exists_rc not in (0, MISSING_APP):
        raise DokkuError(
            f"Could not inspect the Dokku App over SSH (exit {exists_rc}). "
            "The host was not changed."
        )
    if exists_rc == 0:
        return outcome(host, app, version, [], True, False)
    if module.check_mode:
        return outcome(host, app, version, ["create"], False, True)
    create_rc, _create_out = remote(module, base, ["apps:create", app])
    if create_rc != 0:
        create_failure(module, base, host, app, version, create_rc)
    return outcome(host, app, version, ["create"], True, False)


def main():
    module = AnsibleModule(
        argument_spec={
            "host": {"type": "str", "required": True},
            "app": {"type": "str", "required": True},
            "port": {"type": "int"},
            "private_key": {"type": "path", "no_log": True},
            "known_hosts": {"type": "path"},
            "ssh_config": {"type": "path"},
            "executable": {"type": "str", "default": "ssh"},
        },
        supports_check_mode=True,
    )
    try:
        result = ensure(module)
    except DokkuError as exc:
        module.fail_json(msg=str(exc), **exc.result)
    module.exit_json(**result)


if __name__ == "__main__":
    main()
