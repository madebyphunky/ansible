#!/usr/bin/env python3
"""Isolated native CLI double; never connects to a server."""

import json
import os
import stat
import sys
from pathlib import Path

import yaml

args = sys.argv[1:]
state_path = Path(os.environ["KAMAL_TEST_STATE"])
state = json.loads(state_path.read_text())
config_path = Path(args[args.index("--config-file") + 1])
config = yaml.safe_load(config_path.read_text())
assert config["service"] == "example"
assert "--skip-hooks" in args
if config_path.name.startswith("ansible-kamal-"):
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
state.setdefault("paths", []).append(str(config_path))
state.setdefault("calls", []).append(args)
state_path.write_text(json.dumps(state))
if state.get("fail") or (state.get("fail_bootstrap") and "bootstrap" in args):
    print("do-not-leak-test-secret", file=sys.stderr)
    sys.exit(1)
if "bootstrap" in args:
    assert args[-2:] == ["server", "bootstrap"]
    if not state.get("ineffective"):
        state["hosts"] = ["ready"] * len(state["hosts"])
    state_path.write_text(json.dumps(state))
else:
    assert args[-4:-1] == ["server", "exec", "--raw"]
    assert "docker info" in args[-1]
    if "broken" in state["hosts"]:
        sys.exit(1)
    if state.get("invalid_output"):
        print("unexpected")
    elif not state.get("empty_output"):
        for host in state["hosts"]:
            print("KAMAL_DOCKER_" + host.upper())
