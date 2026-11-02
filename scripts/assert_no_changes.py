#!/usr/bin/env python3
"""Assert a localhost Ansible recap has no changes or failures."""

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
recap = re.search(r"^localhost\s+:.*$", text, re.MULTILINE)
assert recap, text
for field in ("changed", "unreachable", "failed"):
    assert re.search(field + r"=0(?:\s|$)", recap.group()), text
