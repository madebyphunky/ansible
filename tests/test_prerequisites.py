"""Public installed prerequisite Roles, without altering the developer's tooling."""

import os
import subprocess
from pathlib import Path

import pytest

from runner import changed, invoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def prerequisite_packages(tmp_path_factory):
    directory = tmp_path_factory.mktemp("prerequisite-packages")
    for name in ("nodejs", "github"):
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
    return directory


@pytest.fixture
def prerequisite_env(prerequisite_packages):
    env = os.environ.copy()
    env.update(
        ANSIBLE_COLLECTIONS_PATH=str(prerequisite_packages),
        ANSIBLE_PYTHON_INTERPRETER=os.sys.executable,
        ANSIBLE_NOCOLOR="1",
    )
    return env


def executable(tmp_path, name, version):
    path = tmp_path / name
    path.write_text(
        '#!/bin/sh\n[ "$1" = "--version" ] || exit 99\nprintf "%s\\n" '
        + repr(version)
        + "\n"
    )
    path.chmod(0o755)
    return str(path)


def test_existing_node_runtime_is_reused(prerequisite_env, tmp_path):
    node = executable(tmp_path, "node", "v24.10.0")
    npm = executable(tmp_path, "npm", "11.6.0")
    npx = executable(tmp_path, "npx", "11.6.0")
    variables = dict(
        nodejs_node_executable=node,
        nodejs_npm_executable=npm,
        nodejs_npx_executable=npx,
        nodejs_install=False,
    )
    tasks = [
        {
            "name": "Assert public runtime contract",
            "ansible.builtin.assert": {
                "that": [
                    "nodejs_runtime.available",
                    "not nodejs_runtime.planned",
                    "nodejs_runtime.node_major == 24",
                    f'nodejs_runtime.node_path == "{node}"',
                    f'nodejs_runtime.npm_path == "{npm}"',
                    f'nodejs_runtime.npx_path == "{npx}"',
                ]
            },
        }
    ]
    for check in (False, False, True):
        result = invoke(
            variables,
            env=prerequisite_env,
            role="madebyphunky.nodejs.setup",
            check=check,
            tasks_after=tasks,
        )
        assert result.returncode == 0, result.stdout
        assert changed(result) == 0


def test_missing_runtime_check_mode_does_not_install(prerequisite_env, tmp_path):
    missing = str(tmp_path / "missing")
    variables = dict(
        nodejs_node_executable=missing,
        nodejs_npm_executable=missing,
        nodejs_npx_executable=missing,
    )
    tasks = [
        {
            "name": "Assert honest check-mode result",
            "ansible.builtin.assert": {
                "that": [
                    "not nodejs_runtime.available",
                    "nodejs_runtime.planned",
                    'nodejs_runtime.node_path == ""',
                ]
            },
        }
    ]
    result = invoke(
        variables,
        env=prerequisite_env,
        role="madebyphunky.nodejs.setup",
        check=True,
        tasks_after=tasks,
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert not Path(missing).exists()


def test_incompatible_runtime_with_installation_disabled_fails(
    prerequisite_env, tmp_path
):
    variables = dict(
        nodejs_node_executable=executable(tmp_path, "node", "v20.19.0"),
        nodejs_npm_executable=executable(tmp_path, "npm", "10.0.0"),
        nodejs_npx_executable=executable(tmp_path, "npx", "10.0.0"),
        nodejs_install=False,
    )
    result = invoke(variables, env=prerequisite_env, role="madebyphunky.nodejs.setup")
    assert result.returncode != 0
    assert "compatible Node.js runtime" in result.stdout
    assert changed(result) == 0


def test_existing_github_cli_is_reused(prerequisite_env, tmp_path):
    path = executable(tmp_path, "gh", "gh version 2.94.0 (2026-11-02)")
    tasks = [
        {
            "name": "Assert public CLI result",
            "ansible.builtin.assert": {
                "that": [
                    "github_cli_result.available",
                    "not github_cli_result.planned",
                    f'github_cli_result.path == "{path}"',
                ]
            },
        }
    ]
    for check in (False, True):
        result = invoke(
            {"github_cli_executable": path, "github_cli_install": False},
            env=prerequisite_env,
            role="madebyphunky.github.cli",
            check=check,
            tasks_after=tasks,
        )
        assert result.returncode == 0, result.stdout
        assert changed(result) == 0


def test_missing_github_cli_check_mode_does_not_install(prerequisite_env, tmp_path):
    path = str(tmp_path / "missing-gh")
    result = invoke(
        {"github_cli_executable": path},
        env=prerequisite_env,
        role="madebyphunky.github.cli",
        check=True,
        tasks_after=[
            {
                "name": "Assert installation plan",
                "ansible.builtin.assert": {
                    "that": [
                        "not github_cli_result.available",
                        "github_cli_result.planned",
                        'github_cli_result.path == ""',
                    ]
                },
            }
        ],
    )
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert not Path(path).exists()


def test_missing_github_cli_without_installation_fails(prerequisite_env, tmp_path):
    result = invoke(
        {
            "github_cli_executable": str(tmp_path / "missing-gh"),
            "github_cli_install": False,
        },
        env=prerequisite_env,
        role="madebyphunky.github.cli",
    )
    assert result.returncode != 0
    assert "GitHub CLI is missing or unusable" in result.stdout
    assert changed(result) == 0
