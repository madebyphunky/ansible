# madebyphunky.supabase

Independently runnable Roles for hosted Supabase, using
`npx --yes supabase@latest`. Set `supabase_cli_version` to an explicit version
when required. The first version follows the CLI v3 command and JSON contracts;
older versions are unsupported. Structured responses are validated against that
contract. Diff and dry-run responses are rejected before mutation, but some
incompatible create/push responses can only be detected afterward; those failures
retain any partial provider changes for inspection rather than retrying blindly.

| Role | Inputs | Public result |
| --- | --- | --- |
| `madebyphunky.supabase.project` | `supabase_organization`, `supabase_project_name`, creation `supabase_region` and `supabase_project_password`, optional `supabase_project_ref` | `supabase_project_result` |
| `madebyphunky.supabase.auth` | `supabase_project_ref`, `supabase_auth_config` (path to config.toml) | `supabase_auth_result` |
| `madebyphunky.supabase.migrations` | `supabase_project_ref`, `supabase_workdir` (application checkout), `SUPABASE_DB_PASSWORD` | `supabase_migrations_result` |
| `madebyphunky.supabase.credentials` | `supabase_project_ref` | `supabase_credentials_result` |

Run locally with Ansible Core 2.18/2.19 and Python 3.11+ (3.12 tested).
The Roles compose `madebyphunky.nodejs.setup` for Node.js/npm/npx on macOS or
Ubuntu/Debian. Set `supabase_manage_prerequisites: false` to supply your own
Node.js 20+ and npx through `supabase_node_executable` and
`supabase_npx_executable`. File inputs are read on the execution host.

Install sibling Collections with `python scripts/collection_tools.py install`
from the repository root. Example composition: `playbooks/project.yml`.

## Credentials and creation password

Every Role requires `SUPABASE_ACCESS_TOKEN` as an Ansible variable or controller
environment variable. Migrations also require `SUPABASE_DB_PASSWORD`. Explicit
Ansible variables take precedence; explicitly blank credentials fail. No saved
CLI login or local link is used.

For a **new** Project, supply `supabase_project_password` explicitly to the Role.
There is no password generation or environment fallback for this input. For example,
use an Ansible Vault variable as the source:

```yaml
- name: Ensure a hosted Project
  ansible.builtin.include_role:
    name: madebyphunky.supabase.project
  vars:
    supabase_organization: my-organization
    supabase_project_name: my-project
    supabase_region: eu-west-2
    supabase_project_password: "{{ vault_supabase_password }}"
```

The password is marked `no_log` and is never returned in result facts. The CLI
requires it in process arguments during creation, so it can briefly be visible
to local process inspection. Other credentials use the child environment.

An existing Project needs no password input. Supplying a different password does
not rotate it. The Role cannot recover an existing Project's password. For
migrations, pass the current password separately as `SUPABASE_DB_PASSWORD`; the
example playbook maps both inputs from the same securely supplied variable.
Never commit secret values or debug credential variables.

## Project ownership and readiness

An explicit organization resolves against `supabase orgs list`; both its ID and
slug are accepted. With a Project reference, the existing Project must match the
organization and name. Without one, exact organization/name lookup reuses a single
match, creates on zero matches, and fails on ambiguity. A differing supplied
region fails. There is no rename, move, password rotation, deletion, or recreation.
Creation leaves compute and other unexposed options at CLI defaults.

Poll the exact Project for `ACTIVE_HEALTHY`, with `supabase_timeout: 900` seconds
and `supabase_poll_interval: 5` by default. Timeout or failure retains resources;
there is no rollback or automatic creation retry. Nonsecret identities remain in
the result when known; passwords are never returned, including on partial
failure. If creation is indeterminate, inspect the selected organization before
rerunning. Connection strings and the full Marketplace `POSTGRES_*` variable set
are not retrieved.

## Credentials retrieval

`madebyphunky.supabase.credentials` retrieves the Project URL plus publishable and
secret API keys for an exact `supabase_project_ref` via
`supabase projects api-keys --reveal`. Prefer new publishable/secret keys named
`default`; fall back to legacy `anon` / `service_role` when those are absent.
Module and result publication tasks use `no_log`; composers read
`supabase_credentials_result` deliberately. Do not debug that fact. Postgres
connection strings and the full Marketplace `POSTGRES_*` set remain out of
scope; Project URL plus publishable/secret keys are in scope for Application
wiring. Cross-provider composition lives in `madebyphunky.application`
(`docs/design/project-creation.md`).

## Auth configuration

Supply a Supabase `config.toml`. Only its explicitly declared `[auth]` settings
and nested Auth tables are staged. CLI-supported settings, including SMTP/OAuth,
are accepted; omitted remote settings remain unchanged. An empty array explicitly
clears a list. Declared Auth `content_path` files are copied into the isolated
workdir; missing or absolute paths fail before the CLI runs. The Role compares
with `config diff`, ignores remote-only fields, and uses `config push` when
required. Declared masked secrets are checked by `config push` using the CLI's
digest comparison, preserving repeat-run idempotency. Unsupported, missing,
gated, or unapplied settings fail rather than count as success.

The application file is never modified. Temporary files live in a private directory
and are removed afterward. Use `env(NAME)` references for Auth secrets, with those
environment variables on the execution host. Ambient `SUPABASE_*` variables are
removed from child processes except explicit access token/database password and
the isolated CLI home, to prevent CLI environment overlays changing ownership.
Use other environment names for Auth secret references.

Project references must be the exact 20-character lowercase Supabase ref.

## Migrations

The Role copies `supabase/migrations` from `supabase_workdir` into a private workdir,
runs `db push --remote=REF --skip-vault --dry-run`, then pushes pending migrations
with explicit noninteractive consent. It does not copy application config, seed
files, or CLI link state. It never resets, repairs history, rolls back, pushes
Vault secrets, or requests `--include-all`, roles, or seeds.

Migration reconciliation follows the CLI's version history, not SQL checksums.
Editing an already-applied migration does not cause reapplication. Application
authors own SQL contents and destructive statements. A failed run can have applied
some pending migrations; inspect CLI history before resolving and rerunning.

## Check mode and verification

Check mode validates local inputs and returns `inspection_limited: true` with a
conservative change plan. It performs no CLI calls, downloads, installations, or
provider writes. It does not claim to have inspected remote state. Local input
validation also runs before prerequisite installation in normal mode.

Installed-Role contract tests use a stateful CLI double matching official v3
structured responses. They cover adoption, ambiguity, region conflicts, secret
redaction, sparse Auth ownership, content_path staging, migrations, check mode,
and partial failures. The Molecule live scenario and protected workflow exist,
and protected live acceptance passed on 2026-11-03 with Supabase CLI 3.0.0,
including verified cleanup. See [verification evidence](../../docs/supabase-verification.md)
for the tested commit, coverage, versions, and limitations. Multi-provider
Application setup live expectations (pending until recorded) are in
[Application live verification](../../docs/application-live-verification.md).
