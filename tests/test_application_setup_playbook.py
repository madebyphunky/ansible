"""Phased Application setup playbook contracts with provider CLI doubles."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = "ansible_collections/madebyphunky/application/playbooks/setup.yml"
SHA = "a" * 40


@pytest.fixture
def application_setup(installed, tmp_path):
    vercel_state = tmp_path / "vercel.json"
    supabase_state = tmp_path / "supabase.json"
    vercel_state.write_text(
        json.dumps(
            {
                "calls": [],
                "commits": [SHA],
                "envs": [],
                "user": "tester",
                "team_id": "team_test",
                "account_id": "team_test",
            }
        )
    )
    supabase_state.write_text(
        json.dumps(
            {
                "calls": [],
                "api_keys": [
                    {
                        "name": "default",
                        "type": "publishable",
                        "api_key": "sb_publishable_test",
                    },
                    {
                        "name": "default",
                        "type": "secret",
                        "api_key": "sb_secret_test_value",
                    },
                ],
            }
        )
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    fixture_dir = Path(__file__).parent / "fixtures"
    npx = tools / "npx"
    npx.write_text(
        "#!/usr/bin/env python3\n"
        "import runpy\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"fixture_dir = Path({str(fixture_dir)!r})\n"
        "original = sys.argv[0]\n"
        "args = sys.argv[1:]\n"
        "sys.argv = [original] + args\n"
        "import os\n"
        "if any(arg.startswith('supabase@') for arg in args):\n"
        "    runpy.run_path(str(fixture_dir / 'supabase_cli.py'), run_name='__main__')\n"
        "elif any(arg.startswith('vercel@') for arg in args):\n"
        "    os.environ['APPLICATION_FIXTURE_PROVIDER'] = 'vercel'\n"
        "    runpy.run_path(str(fixture_dir / 'vercel_cli.py'), run_name='__main__')\n"
        "else:\n"
        "    print('Unhandled application npx invocation: ' + ' '.join(args), file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
    )
    npx.chmod(0o755)
    gh = tools / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import runpy\n"
        "import sys\n"
        f"fixture_dir = __import__('pathlib').Path({str(fixture_dir)!r})\n"
        "os.environ['APPLICATION_FIXTURE_PROVIDER'] = 'github'\n"
        "sys.argv[0] = str(fixture_dir / 'gh')\n"
        "runpy.run_path(str(fixture_dir / 'vercel_cli.py'), run_name='__main__')\n"
    )
    gh.chmod(0o755)

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
        VERCEL_CONTRACT_STATE=str(vercel_state),
        ANSIBLE_SUPABASE_CONTRACT_STATE=str(supabase_state),
        VERCEL_TOKEN="dummy-vercel",
        GH_TOKEN="dummy-github",
        SUPABASE_ACCESS_TOKEN="dummy-explicit-token",
    )
    # Route gh fixture token expectation.
    env["VERCEL_CONTRACT_EXPECT_GITHUB"] = "dummy-github"
    env["VERCEL_CONTRACT_EXPECT_VERCEL"] = "dummy-vercel"

    playbook = Path(installed) / PLAYBOOK
    assert playbook.is_file(), playbook

    def run(extra_vars=None, verbose=False):
        variables = {
            "vercel_project_name": "test-project",
            "vercel_scope_type": "team",
            "vercel_scope_id": "team_test",
            "vercel_source_mode": "ensure",
            "github_owner": "tester",
            "github_repository": "demo",
            "vercel_manage_prerequisites": False,
            "vercel_npx_executable": str(tools / "npx"),
            "vercel_gh_executable": str(tools / "gh"),
            "vercel_poll_interval": 1,
            "supabase_organization": "org-id",
            "supabase_project_name": "test-project",
            "supabase_project_password": "caller-password-0123456789",
            "supabase_region": "eu-west-2",
            "supabase_manage_prerequisites": False,
            "supabase_npx_executable": str(tools / "npx"),
            "supabase_poll_interval": 1,
            "SUPABASE_ACCESS_TOKEN": "dummy-explicit-token",
        }
        variables.update(extra_vars or {})
        vars_file = tmp_path / "extra-vars.json"
        vars_file.write_text(json.dumps(variables))
        args = [
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            "-e",
            f"@{vars_file}",
            str(playbook),
        ]
        if verbose:
            args.append("-vv")
        return subprocess.run(
            args,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            cwd=str(tmp_path),
        )

    def read_vercel():
        return json.loads(vercel_state.read_text())

    def read_supabase():
        return json.loads(supabase_state.read_text())

    return run, checkout, read_vercel, read_supabase, tools


def test_setup_infra_only_stops_cleanly_without_source(application_setup):
    run, _, read_vercel, read_supabase, _ = application_setup
    result = run()
    assert result.returncode == 0, result.stdout
    assert "Skipping migrations" in result.stdout
    assert "Skipping Auth" in result.stdout
    assert "Skipping env wiring" in result.stdout
    assert "Skipping production Deployment" in result.stdout
    assert read_vercel()["project"]["name"] == "test-project"
    assert read_supabase()["projects"][0]["ref"] == "abcdefghijabcdefghij"
    assert not any(
        call["operation"] == "projects api-keys" for call in read_supabase()["calls"]
    )


def _seed_application_source(checkout):
    migrations = checkout / "supabase" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "20261104090000_widgets.sql").write_text(
        "create table widgets (id int);"
    )
    (checkout / "supabase" / "config.toml").write_text(
        '[auth]\nsite_url = "http://localhost:3000"\n'
    )
    auth = checkout / "auth.toml"
    auth.write_text('[auth]\nsite_url = "http://localhost:3000"\n')
    return auth


def test_setup_continues_through_env_when_workdir_ready(application_setup):
    run, checkout, read_vercel, read_supabase, _ = application_setup
    auth = _seed_application_source(checkout)
    result = run(
        {
            "application_workdir": str(checkout),
            "application_auth_config": str(auth),
        },
        verbose=True,
    )
    assert result.returncode == 0, result.stdout
    assert "Skipping migrations" not in result.stdout
    assert "Skipping Auth" not in result.stdout
    assert "Skipping env wiring" not in result.stdout
    assert "Skipping production Deployment" in result.stdout
    assert "Skipping Auth Site URL update" not in result.stdout
    assert "sb_secret_test_value" not in result.stdout
    assert (checkout / ".env.local").exists()
    assert (
        "SUPABASE_SECRET_KEY=sb_secret_test_value"
        in (checkout / ".env.local").read_text()
    )
    assert {item["key"] for item in read_vercel()["envs"]} >= {
        "NEXT_PUBLIC_SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
    }
    assert any(call["operation"] == "db push" for call in read_supabase()["calls"])
    assert any(
        call["operation"] == "projects api-keys" for call in read_supabase()["calls"]
    )
    assert not read_vercel().get("deployments")


def test_setup_deploys_exact_sha_and_updates_auth_site_url(application_setup):
    run, checkout, read_vercel, read_supabase, _ = application_setup
    auth = _seed_application_source(checkout)
    result = run(
        {
            "application_workdir": str(checkout),
            "application_auth_config": str(auth),
            "vercel_git_sha": SHA,
        },
        verbose=True,
    )
    assert result.returncode == 0, result.stdout
    assert "Skipping production Deployment" not in result.stdout
    assert "Skipping Auth Site URL update" not in result.stdout
    assert "sb_secret_test_value" not in result.stdout
    deployments = read_vercel().get("deployments", [])
    assert len(deployments) == 1
    assert deployments[0]["gitSource"]["sha"] == SHA
    auth_state = read_supabase().get("auth", {})
    assert auth_state.get("site_url") == "https://test-deployment.vercel.app"
    assert auth_state.get("additional_redirect_urls") == [
        "https://test-deployment.vercel.app/**",
        "http://localhost:3000/**",
    ]


def test_setup_rejects_play_level_vercel_deploy(application_setup):
    run, checkout, _, _, _ = application_setup
    auth = _seed_application_source(checkout)
    result = run(
        {
            "application_workdir": str(checkout),
            "application_auth_config": str(auth),
            "vercel_deploy": True,
            "vercel_git_sha": SHA,
        }
    )
    assert result.returncode != 0
    assert "Do not set vercel_deploy on the Application setup playbook" in result.stdout


def test_setup_rejects_play_level_supabase_auth_config(application_setup):
    run, checkout, _, _, _ = application_setup
    auth = _seed_application_source(checkout)
    result = run(
        {
            "application_workdir": str(checkout),
            "supabase_auth_config": str(auth),
            "vercel_git_sha": SHA,
        }
    )
    assert result.returncode != 0
    assert (
        "Do not set supabase_auth_config on the Application setup playbook"
        in result.stdout
    )
