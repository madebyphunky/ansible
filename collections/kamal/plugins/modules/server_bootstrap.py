#!/usr/bin/python
# Copyright (c) 2026 madebyphunky
# SPDX-License-Identifier: MIT
"""Use Kamal's SSH transport and bootstrap without deploying an Application."""

from __future__ import annotations

import os
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.yaml import yaml_dump

DOCUMENTATION = r"""
---
module: server_bootstrap
short_description: Prepare existing hosts for Kamal without deploying
description:
  - Inspects Docker through Kamal, bootstraps only when missing, and verifies daemon access.
  - Run on the controller. Requires Kamal 2.12, SSH access, and a valid native config.
  - Hooks are disabled. Native server exec writes audit entries even in check mode.
options:
  workdir:
    type: path
    required: true
    description: Controller checkout directory.
  config_file:
    type: path
    description: Native config path relative to workdir or absolute; exclusive with config.
  config:
    type: dict
    description: Native config values, serialized temporarily; exclusive with config_file.
  executable:
    type: str
    default: kamal
    description: Existing Kamal executable or wrapper.
  destination:
    type: str
    default: ''
    description: Native destination selector.
  environment:
    type: dict
    default: {}
    description: Redacted environment overrides for Kamal processes.
author: madebyphunky
"""
EXAMPLES = r"""
- name: Prepare existing hosts
  madebyphunky.kamal.server_bootstrap:
    workdir: /srv/checkouts/my-app
    config_file: config/deploy.yml
"""
RETURN = r"""
ready:
  type: bool
  returned: success
  description: Whether all selected hosts have accessible Docker daemons.
planned:
  type: bool
  returned: success
  description: Whether check mode predicts bootstrap.
"""

# Fixed command, never interpolates caller data. Nonzero Docker/SSH failures are
# errors, not evidence of absence. Raw output emits one state per selected host.
PROBE = (
    "if command -v docker >/dev/null 2>&1; then "
    "docker --version >/dev/null && docker info >/dev/null && "
    "printf 'KAMAL_DOCKER_READY\\n'; else printf 'KAMAL_DOCKER_MISSING\\n'; fi"
)


def main():
    module = AnsibleModule(
        argument_spec={
            "workdir": {"type": "path", "required": True},
            "config_file": {"type": "path"},
            "config": {"type": "dict", "no_log": True},
            "executable": {"type": "str", "default": "kamal"},
            "destination": {"type": "str", "default": ""},
            "environment": {"type": "dict", "default": {}, "no_log": True},
        },
        mutually_exclusive=[("config_file", "config")],
        required_one_of=[("config_file", "config")],
        supports_check_mode=True,
    )
    params = module.params
    workdir = os.path.abspath(params["workdir"])
    if not os.path.isdir(workdir):
        module.fail_json(msg="kamal_workdir must be an existing controller directory.")
    executable = module.get_bin_path(params["executable"], required=True)
    temporary = None
    result = None
    error = None
    bootstrap_attempted = False
    try:
        config_file = params["config_file"]
        if config_file is not None:
            config_file = os.path.abspath(os.path.join(workdir, config_file))
            if not os.path.isfile(config_file):
                raise ValueError(
                    "Kamal config file does not exist or is not a regular file."
                )
        else:
            # mkstemp creates a private 0600 file even with a permissive umask.
            descriptor, temporary = tempfile.mkstemp(
                suffix=".yml", prefix="ansible-kamal-"
            )
            with os.fdopen(descriptor, "w") as stream:
                stream.write(yaml_dump(params["config"]))
            config_file = temporary
        base = [executable, "--config-file", config_file, "--skip-hooks"]
        if params["destination"]:
            base += ["--destination", params["destination"]]

        def run(arguments, stage):
            rc, stdout, _ = module.run_command(
                base + arguments,
                cwd=workdir,
                environ_update={
                    str(k): str(v) for k, v in params["environment"].items()
                },
            )
            if rc:
                # CLI errors can contain rendered config, environment, or secrets.
                raise ValueError(
                    f"Kamal {stage} failed (exit {rc}). Check native configuration, SSH "
                    "access, and Docker daemon permissions; CLI output withheld to protect secrets."
                )
            return stdout

        def inspect():
            output = run(["server", "exec", "--raw", PROBE], "Docker inspection")
            states = output.splitlines()
            if not states or any(
                state not in ("KAMAL_DOCKER_READY", "KAMAL_DOCKER_MISSING")
                for state in states
            ):
                raise ValueError(
                    "Kamal Docker inspection returned unrecognized or empty host state."
                )
            return "KAMAL_DOCKER_MISSING" not in states

        ready = inspect()
        changed = not ready
        if changed and not module.check_mode:
            bootstrap_attempted = True
            run(["server", "bootstrap"], "server bootstrap")
            if not inspect():
                raise ValueError(
                    "Kamal bootstrap completed but Docker is still absent on selected hosts."
                )
            ready = True
        result = dict(
            changed=changed, ready=ready, planned=changed and module.check_mode
        )
    except (OSError, ValueError) as exc:
        error = str(exc)
    finally:
        if temporary is not None:
            os.unlink(temporary)
    if error:
        module.fail_json(msg=error, changed=bootstrap_attempted)
    module.exit_json(**result)


if __name__ == "__main__":
    main()
