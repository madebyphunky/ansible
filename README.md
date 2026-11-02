# madebyphunky Ansible Collections

Small reusable Roles that Agents run to maintain project infrastructure. This
repository contains independently installable provider Collections; the repository
root is no longer an Ansible Collection.

| Collection | Public Role | Purpose |
| --- | --- | --- |
| `madebyphunky.gandi` | `madebyphunky.gandi.livedns` | Converge explicitly owned Gandi LiveDNS record sets. |
| `madebyphunky.vercel` | `madebyphunky.vercel.project` | Ensure a Vercel Project and optional GitHub repository/production deployment. |
| `madebyphunky.github` | `madebyphunky.github.cli` | Ensure GitHub CLI is available. |
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

## Migration from madebyphunky.infra

Replace `madebyphunky.infra.dns_gandi_livedns` with
`madebyphunky.gandi.livedns`, including the Collection example playbook invocation.
The old Role is removed; there is no compatibility alias. Existing Gandi input
variables, environment fallback, Managed-set ownership, and DNS behaviour are
unchanged. Install `madebyphunky.gandi` and update consumer playbooks before running.
An old locally installed `madebyphunky.infra` package is not automatically removed
from your machine; the new distribution does not include it.

The Gandi source moved to `collections/gandi`. Documentation, examples, CI, and
live Molecule tests now use the new public name. See
[the migration decision](docs/adr/0001-provider-scoped-collections.md).

## Credentials

Vercel/GitHub Roles accept explicit Ansible variables named `VERCEL_TOKEN` and
`GH_TOKEN`, falling back to the controller environment variables with those same
names. The names are shared across provider Roles, matching their official CLIs.
Explicit variables take precedence. Credentials are passed through process
environments and redacted rather than included in command arguments.

Gandi continues to use `gandi_livedns_personal_access_token`, falling back to
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
[Vercel live verification](docs/vercel-live-verification.md). Local Vercel/GitHub acceptance passed on 2026-11-02, including historical
production reuse and exact-resource cleanup. The renamed Gandi Role also passed live acceptance and verified cleanup;
its migration evidence is recorded separately. Missing credentials never count as a passing live run.
