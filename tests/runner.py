"""Exercise the installed public Role, without exposing credentials in shell arguments."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROLE = "madebyphunky.infra.dns_gandi_livedns"


def invoke(variables, *, env=None, check=False, verbose=False):
    play = [
        {
            "name": "Public Role contract",
            "hosts": "localhost",
            "gather_facts": False,
            "vars": variables,
            "roles": [ROLE],
        }
    ]
    with tempfile.TemporaryDirectory(prefix="infra-play-") as directory:
        path = Path(directory) / "play.json"
        path.write_text(json.dumps(play))
        path.chmod(0o600)
        command = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(path)]
        if check:
            command.append("--check")
        if verbose:
            command.append("-vvv")
        return subprocess.run(
            command,
            env=env or os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )


def changed(result):
    match = re.search(r"localhost\s+:.*?changed=(\d+)", result.stdout)
    assert match, result.stdout
    return int(match.group(1))
