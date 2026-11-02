#!/usr/bin/python
# Copyright (c) 2026 madebyphunky
# SPDX-License-Identifier: MIT
"""Read-only runtime discovery; never runs npm install or npx package resolution."""

from __future__ import annotations

import os
import platform
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.sys_info import get_distribution

DOCUMENTATION = r"""
---
module: runtime_info
short_description: Inspect a Node.js runtime without downloading packages
description:
  - Resolve node, npm, and npx and inspect their version commands.
  - This module never downloads or installs anything, including in check mode.
options:
  node_executable:
    type: str
    default: node
    description: Node.js executable or absolute path.
  npm_executable:
    type: str
    default: npm
    description: npm executable or absolute path.
  npx_executable:
    type: str
    default: npx
    description: npx executable or absolute path.
  compatible_majors:
    type: list
    elements: int
    default: [22, 24, 26]
    description: Node.js major releases accepted for reuse.
author: madebyphunky
"""
EXAMPLES = r"""
- name: Inspect a local runtime
  madebyphunky.nodejs.runtime_info:
"""
RETURN = r"""
node_path:
  type: str
  returned: always
  description: Resolved Node.js path, or an empty string.
node_major:
  type: int
  returned: always
  description: Detected Node.js major, or zero.
available:
  type: bool
  returned: always
  description: Whether all three tools are present and Node.js is compatible.
"""


def main():
    module = AnsibleModule(
        argument_spec={
            "node_executable": {"type": "str", "default": "node"},
            "npm_executable": {"type": "str", "default": "npm"},
            "npx_executable": {"type": "str", "default": "npx"},
            "compatible_majors": {
                "type": "list",
                "elements": "int",
                "default": [22, 24, 26],
            },
        },
        supports_check_mode=True,
    )
    paths, valid = {}, {}
    major = 0
    for tool in ("node", "npm", "npx"):
        path = module.get_bin_path(module.params[tool + "_executable"], required=False)
        paths[tool + "_path"] = path or ""
        valid[tool] = False
        if path:
            command_env = {"NO_UPDATE_NOTIFIER": "1"}
            if paths.get("node_path"):
                command_env["PATH"] = (
                    os.path.dirname(paths["node_path"])
                    + os.pathsep
                    + os.environ.get("PATH", "")
                )
            code, stdout, _ = module.run_command(
                [path, "--version"], environ_update=command_env
            )
            match = re.match(r"^v?(\d+)\.", stdout.strip())
            valid[tool] = code == 0 and match is not None
            if tool == "node" and valid[tool]:
                major = int(match.group(1))
    module.exit_json(
        changed=False,
        node_major=major,
        available=all(valid.values()) and major in module.params["compatible_majors"],
        system=platform.system(),
        distribution=get_distribution() or "",
        **paths,
    )


if __name__ == "__main__":
    main()
