# madebyphunky Ansible Collections

Small reusable Roles that Agents run to maintain project infrastructure. This
repository contains independently installable provider Collections; the repository
root contains shared tooling and documentation.

| Collection | Public Role | Purpose |
| --- | --- | --- |
| `madebyphunky.gandi` | `madebyphunky.gandi.livedns` | Converge explicitly owned Gandi LiveDNS record sets. |
| `madebyphunky.vercel` | `madebyphunky.vercel.project`, `.env` | Ensure a Vercel Project, optional GitHub repository/production deployment, and production application environment variables. |
| `madebyphunky.github` | `madebyphunky.github.cli` | Ensure GitHub CLI is available. |
| `madebyphunky.supabase` | `madebyphunky.supabase.project`, `.auth`, `.migrations`, `.credentials` | Ensure hosted Projects, configure Auth, apply SQL migrations, and retrieve Project URL/API keys through the CLI. |
| `madebyphunky.nodejs` | `madebyphunky.nodejs.setup` | Ensure a compatible Node.js runtime, npm, and npx are available. |

## Install

Use a checkout and Ansible Core 2.18 or 2.19 with a supported controller Python.
Install the local Collections and their declared dependencies in dependency order:

```sh
git clone git@github.com:madebyphunky/ansible.git
cd ansible
python scripts/collection_tools.py install
```

The Python used for this command must have Ansible installed. This installs local
sibling Collections before their consumers, avoiding registry lookups for packages
that have not been published to Galaxy. External dependencies are installed by
Galaxy. Use `--path /some/collection-directory` for an isolated installation and
set `ANSIBLE_COLLECTIONS_PATH` to that directory for subsequent playbook runs.

Build distributable archives without installing them:

```sh
python scripts/collection_tools.py build
```

Archives are written to `artifacts/`. Each Collection can also be built independently
from its own source directory. See each Collection's README and Role argument
specifications for inputs, runtime prerequisites, and execution examples. Thin
example playbooks gather no unnecessary facts and default to localhost.

## Credentials

Vercel/GitHub Roles accept explicit Ansible variables named `VERCEL_TOKEN` and
`GH_TOKEN`, falling back to the controller environment variables with those same
names. The names are shared across provider Roles, matching their official CLIs.
Explicit variables take precedence. Credentials are passed through process
environments and redacted rather than included in command arguments.

Supabase Roles use `SUPABASE_ACCESS_TOKEN`; migrations also use
`SUPABASE_DB_PASSWORD`, with explicit variables overriding controller environment
values. New Projects require an explicit `supabase_project_password` Role input;
there is no automatic password generation or creation-password environment fallback.
See [Supabase credential handling](collections/supabase/README.md#credentials-and-creation-password)
for the creation CLI process-argument tradeoff.

Gandi uses `gandi_livedns_personal_access_token`, falling back to
`GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN`. Never commit tokens, secret environment files,
vault files containing credentials, or real credentials in examples.

## Development

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/collection_tools.py install
ansible-lint
black --check tests scripts collections
pytest -q tests
```

Contract tests build and install the actual Collections into isolated paths and
invoke public Roles. Isolated provider/CLI doubles keep PR checks credential-free.
The Gandi test provider records calls so validation-before-mutation, ownership,
redaction, idempotency, and stop-on-failure promises are observable.

Live acceptance is separate and uses protected GitHub Actions environments,
explicit test accounts, unique disposable resources, and exact-identity cleanup.
See [Gandi live verification](docs/live-verification.md) and
[Vercel live verification](docs/vercel-live-verification.md). Local acceptance
passed for both on 2026-11-02, including verified cleanup. Missing credentials
never count as a passing live run.

Supabase contracts use an isolated CLI double. Protected live acceptance passed
on 2026-11-03, including verified cleanup. See [Supabase verification](docs/supabase-verification.md)
for the tested commit, versions, coverage, and limitations.
