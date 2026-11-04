import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from runner import invoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def installed(tmp_path_factory):
    directory = tmp_path_factory.mktemp("installed")
    # Force every package into the isolated path even if CI has the same version installed.
    for name in (
        "nodejs",
        "github",
        "gandi",
        "spaceship",
        "vercel",
        "supabase",
        "application",
    ):
        subprocess.run(
            [
                "ansible-galaxy",
                "collection",
                "build",
                str(ROOT / "collections" / name),
                "--output-path",
                str(directory),
            ],
            check=True,
        )
        archive = next(directory.glob(f"madebyphunky-{name}-*.tar.gz"))
        subprocess.run(
            [
                "ansible-galaxy",
                "collection",
                "install",
                str(archive),
                "--no-deps",
                "--force",
                "-p",
                str(directory),
            ],
            check=True,
        )
    # Replace only the provider in an isolated test installation. The packaged Role stays intact.
    provider = (
        directory
        / "ansible_collections/community/general/plugins/modules/gandi_livedns.py"
    )
    provider.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/gandi_livedns.py", provider)
    return directory


@pytest.fixture
def contract(installed, tmp_path):
    state = tmp_path / "state.json"
    env = os.environ.copy()
    env.update(
        ANSIBLE_COLLECTIONS_PATH=str(installed),
        INFRA_TEST_STATE=str(state),
        ANSIBLE_LOCALHOST_WARNING="False",
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_PYTHON_INTERPRETER=os.sys.executable,
        GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN="dummy-environment-token",
    )
    variables = {
        "gandi_livedns_zone": "example.com",
        "gandi_livedns_personal_access_token": "dummy-variable-token",
        "gandi_livedns_records": [
            {"name": "www", "type": "A", "ttl": 300, "values": ["192.0.2.1"]}
        ],
    }

    def run(overrides=None, **kwargs):
        return invoke(variables | (overrides or {}), env=env, **kwargs)

    def data():
        return (
            json.loads(state.read_text())
            if state.exists()
            else {"records": {}, "calls": []}
        )

    return run, variables, env, data
