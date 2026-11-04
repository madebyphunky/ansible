"""Local env Role contracts for madebyphunky.application."""

import os
import subprocess
from pathlib import Path

import pytest

from runner import changed, invoke

ROLE = "madebyphunky.application.local_env"


@pytest.fixture
def application_env(installed, tmp_path):
    checkout = tmp_path / "app"
    checkout.mkdir()
    (checkout / ".gitignore").write_text(".env*.local\n")
    subprocess.run(["git", "init"], cwd=checkout, check=True, capture_output=True)
    env = os.environ.copy()
    env.update(
        ANSIBLE_COLLECTIONS_PATH=str(installed),
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_LOCALHOST_WARNING="False",
        ANSIBLE_PYTHON_INTERPRETER=os.sys.executable,
    )
    variables = {
        "application_workdir": str(checkout),
        "application_env": {
            "NEXT_PUBLIC_SUPABASE_URL": "https://abcdefghijabcdefghij.supabase.co",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
        },
    }

    def run(overrides=None, **kwargs):
        return invoke(
            variables | (overrides or {}),
            env=env,
            role=ROLE,
            tasks_after=kwargs.pop(
                "tasks_after",
                [
                    {
                        "name": "Read public local env result",
                        "ansible.builtin.debug": {"var": "application_local_env_result"},
                    }
                ],
            ),
            **kwargs
        )

    return run, checkout


def test_local_env_writes_gitignored_dotenv_and_redacts_secrets(application_env):
    run, checkout = application_env
    result = run(verbose=True)
    assert result.returncode == 0, result.stdout
    assert changed(result) == 1
    assert "sb_secret_test_value" not in result.stdout
    content = (checkout / ".env.local").read_text()
    assert "NEXT_PUBLIC_SUPABASE_URL=https://abcdefghijabcdefghij.supabase.co" in content
    assert "SUPABASE_SECRET_KEY=sb_secret_test_value" in content
    second = run()
    assert second.returncode == 0, second.stdout
    assert changed(second) == 0


def test_local_env_refuses_when_not_gitignored(application_env):
    run, checkout = application_env
    (checkout / ".gitignore").write_text("node_modules/\n")
    result = run()
    assert result.returncode != 0
    assert "gitignor" in result.stdout.lower()
    assert not (checkout / ".env.local").exists()


def test_local_env_check_mode_does_not_write(application_env):
    run, checkout = application_env
    result = run(check=True)
    assert result.returncode == 0, result.stdout
    assert not (checkout / ".env.local").exists()
