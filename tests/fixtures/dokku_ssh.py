#!/usr/bin/env python3
"""SSH/Dokku double. Records argv and never opens a network connection."""

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state_path = Path(os.environ["DOKKU_TEST_STATE"])
state = json.loads(state_path.read_text())
state.setdefault("calls", []).append(args)
state.setdefault("apps", [])
state_path.write_text(json.dumps(state))

if state.get("fail") == "ssh":
    print("do-not-leak-test-secret", file=sys.stderr)
    sys.exit(255)

try:
    destination = next(
        index for index, arg in enumerate(args) if arg.startswith("dokku@")
    )
except StopIteration:
    sys.exit(255)
remote = args[destination + 1 :]
if not remote:
    sys.exit(255)

command, command_args = remote[0], remote[1:]
if command == "version":
    if "version_raw" in state:
        sys.stdout.write(state["version_raw"])
        sys.exit(0)
    print("dokku version " + state.get("version", "0.38.34"))
    sys.exit(0)

if command == "apps:exists":
    app = command_args[0]
    if app in state["apps"]:
        sys.exit(0)
    print(f" !     App {app} does not exist", file=sys.stderr)
    sys.exit(20)

if command == "apps:create":
    app = command_args[0]
    if state.get("fail") == "create":
        if state.get("record_partial"):
            state["apps"].append(app)
            state_path.write_text(json.dumps(state))
        print("do-not-leak-test-secret", file=sys.stderr)
        sys.exit(1)
    if app not in state["apps"]:
        state["apps"].append(app)
    state_path.write_text(json.dumps(state))
    print(f"Creating {app}... done")
    sys.exit(0)

sys.exit(255)
