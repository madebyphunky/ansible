# madebyphunky.supabase

Three independently runnable Roles for hosted Supabase, using
`npx --yes supabase@latest`. Set `supabase_cli_version` to an explicit version
when required. The first version follows the CLI v3 command and JSON contracts;
older versions are unsupported. A future incompatible `latest` response fails
rather than triggering a blind mutation.

| Role | Inputs | Public result |
| --- | --- | --- |
| `madebyphunky.supabase.project` | `supabase_organization`, `supabase_project_name`, creation `supabase_region`, optional `supabase_project_ref` | `supabase_project_result` |
| `madebyphunky.supabase.auth` | `supabase_project_ref`, `supabase_auth_config` (path to config.toml) | `supabase_auth_result` |
| `madebyphunky.supabase.migrations` | `supabase_project_ref`, `supabase_workdir` (application checkout), `SUPABASE_DB_PASSWORD` | `supabase_migrations_result` |

Run locally with Ansible Core 2.18/2.19 and Python 3.11+ (3.12 tested).
The Roles compose `madebyphunky.nodejs.setup` for Node.js/npm/npx on macOS or
Ubuntu/Debian. Set `supabase_manage_prerequisites: false` to supply your own
Node.js 20+ and npx through `supabase_node_executable` and
`supabase_npx_executable`. File inputs are read on the execution host.

Install sibling Collections with `python scripts/collection_tools.py install`
from the repository root. Example composition: `playbooks/project.yml`.

## Credentials and initial password

Every Role requires `SUPABASE_ACCESS_TOKEN` as an Ansible variable or controller
environment variable. Migrations also require `SUPABASE_DB_PASSWORD`. Explicit
Ansible variables take precedence; explicitly blank credentials fail. Credentials
are redacted and passed through the child environment, except for the generated
project creation password described below. No saved CLI login or local link is used.

For a **new** Project the Role generates a random initial database password. It is
available as the sensitive, non-cacheable fact `supabase_project_initial_password`,
with `supabase_project_result.password_change_required: true`. Capture it into your
secret manager using a `no_log: true` task, then change it in Supabase and update
consumers. Never debug this fact or write it into a repository. The CLI requires
this generated password in process arguments during creation, so it can briefly be
visible to local process inspection; logs and public result facts omit it. This
tradeoff applies to newly generated passwords only.

The Role cannot recover or rotate an existing Project's password. The initial
password fact is empty on adoption/repeat runs. After creating and before rotating,
it can be passed directly to the migrations Role as `SUPABASE_DB_PASSWORD` under
`no_log: true`. After rotation, supply the current password from your secret manager.

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
the result when known; the initial password is preserved separately on partial
failure. If creation is indeterminate, inspect the selected organization before
rerunning. No API keys or connection strings are retrieved.

## Auth configuration

Supply a Supabase `config.toml`. Only its explicitly declared `[auth]` settings
and nested Auth tables are staged. CLI-supported settings, including SMTP/OAuth,
are accepted; omitted remote settings remain unchanged. An empty array explicitly
clears a list. The Role compares with `config diff`, ignores remote-only fields,
and uses `config push` when required. Declared masked secrets are checked by
`config push` using the CLI's digest comparison, preserving repeat-run idempotency.
Unsupported, missing, gated, or unapplied settings fail rather than count as success.

The application file is never modified. Temporary files live in a private directory
and are removed afterward. Use `env(NAME)` references for Auth secrets, with those
environment variables on the execution host. Ambient `SUPABASE_*` variables are
removed from child processes except explicit access token/database password and
the isolated CLI home, to prevent CLI environment overlays changing ownership.
Use other environment names for Auth secret references.

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
redaction, sparse Auth ownership, migrations, check mode, and partial failures.
Live provider acceptance has **not** been run for this first version; these tests
do not establish live readiness. See the repository's Supabase verification notes.
