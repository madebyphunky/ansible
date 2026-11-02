#!/usr/bin/python
# Copyright (c) 2026 madebyphunky
# SPDX-License-Identifier: MIT
"""Inspect GitHub CLI without reading authentication or performing network requests."""

from __future__ import annotations

import platform
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.sys_info import get_distribution

DOCUMENTATION = r"""
---
module: cli_info
short_description: Inspect an existing GitHub CLI installation
description:
  - Resolve gh and run its local version command without authenticating.
options:
  executable:
    type: str
    default: gh
    description: Executable name or absolute path.
author: madebyphunky
"""
EXAMPLES = r"""
- name: Inspect GitHub CLI
  madebyphunky.github.cli_info:
"""
RETURN = r"""
path:
  type: str
  returned: always
  description: Resolved path, or an empty string.
available:
  type: bool
  returned: always
  description: Whether a working GitHub CLI was found.
"""


def main():
    module = AnsibleModule(
        argument_spec={"executable": {"type": "str", "default": "gh"}},
        supports_check_mode=True,
    )
    path = module.get_bin_path(module.params["executable"], required=False)
    available = False
    if path:
        code, stdout, _ = module.run_command(
            [path, "--version"], environ_update={"GH_NO_UPDATE_NOTIFIER": "1"}
        )
        available = (
            code == 0 and re.match(r"^gh version \d+\.", stdout.strip()) is not None
        )
    module.exit_json(
        changed=False,
        path=path or "",
        available=available,
        system=platform.system(),
        distribution=get_distribution() or "",
    )


if __name__ == "__main__":
    main()
