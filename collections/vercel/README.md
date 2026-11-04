# madebyphunky.vercel

The `madebyphunky.vercel.project` Role provisions an explicitly scoped Vercel
Project, optionally connects or creates a GitHub repository, and optionally makes
an exact commit the active production deployment. It composes
`madebyphunky.nodejs.setup` and `madebyphunky.github.cli` prerequisites when needed.

The `madebyphunky.vercel.env` Role ensures declared application environment
variables for the **production** target only. `NEXT_PUBLIC_*` keys use type
`encrypted`; other keys use `sensitive`. Unspecified remote variables are
preserved. Preview/development targets are refused. Existing sensitive values
are not re-read; re-runs leave them unchanged once present.

Install the sibling Node.js and GitHub Collections first, then this Collection.
See the repository guide for the multi-Collection build and installation command.
Use Ansible Core 2.18 or 2.19 and a supported Python. The Role runs on macOS or
Ubuntu/Debian hosts supported by its prerequisite Roles. API operations require
HTTPS connectivity to npm, Vercel, and GitHub as applicable.

## Run

Use the thin installed playbook `madebyphunky.vercel.project` with local connection
and explicit input variables, or include the Role in your own playbook. The
playbook defaults to localhost and does not gather general host facts.

```yaml
- name: Provision an empty Project
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - role: madebyphunky.vercel.project
      vercel_project_name: my-project
      vercel_scope_type: team
      vercel_scope_id: team_example
```

Set `VERCEL_TOKEN` in the controller environment using your secret manager. For
GitHub modes supply `GH_TOKEN` too. Explicit Ansible variables with exactly those
uppercase names override environment values. Blank explicit values fail rather
than falling back. These are shared provider-wide credential names. Tokens are
passed to clients only through process environments, redacted from module inputs
and protected by `no_log` on credential-bearing tasks. Never commit real tokens.

## Inputs

The Role argument specification is the machine-readable interface, with default
values in its defaults. Required inputs are `vercel_project_name`,
`vercel_scope_type` (`personal` or `team`), and `vercel_scope_id` (the actual provider
account/team ID, verified before mutation).

| Variable | Default | Behaviour |
| --- | --- | --- |
| `vercel_source_mode` | `none` | `none`, `existing`, or `ensure` a GitHub repository exists and link it. |
| `github_owner`, `github_repository` | Required in GitHub modes | Explicit owner/name; never inferred from login or local Git config. |
| `vercel_project_settings` | `{}` | Supplied camelCase framework, rootDirectory, buildCommand, installCommand, outputDirectory fields. |
| `vercel_deploy` | `false` | Ensure the requested exact commit is active in production. |
| `vercel_git_sha` | Required when deploying | Exact existing 40-character Git commit SHA. |
| `vercel_deployment_timeout` | `900` | Overall provider-operation and wait budget, seconds. |
| `vercel_poll_interval` | `5` | Seconds between readiness/promotion checks. |
| `vercel_retry_failed_deployment` | `false` | Explicitly permit a new deployment after a matching failure. |
| `vercel_manage_prerequisites` | `true` | Compose reusable Node.js and GitHub CLI setup. |
| `vercel_npx_executable`, `vercel_gh_executable`, `vercel_node_executable` | `npx`, `gh`, `node` | Explicit client paths when prerequisite management is disabled. |

GitHub repository creation defaults to private and empty. Existing repository
visibility/content is preserved. An `ensure` run with deployment requested fails
before creating a missing repository because an empty repository cannot contain
the requested commit. Vercel GitHub App access to the repository is a prerequisite
for linking and is not established by a bearer token.

The Role uses `npx --yes vercel@latest` and explicit CLI API requests. It runs in an
isolated working/configuration directory rather than using local Project files or
CLI login state. npm's `--yes` permits package retrieval; Vercel's noninteractive
flag separately prevents prompts. Upstream CLI version changes are intentionally
accepted; credential-free contracts and protected live acceptance catch drift.

## Ownership and deployment

Existing matching resources are reused; a different linked repository fails
without relinking. `none` refuses a Project already linked to Git. Supplied
settings are managed; omitted settings are preserved. Explicit null uses Vercel's
reset semantics: command/output null restores detection, rootDirectory null means
Project root, framework null means no framework.

Linking retains Vercel's native deployments on future pushes. `vercel_deploy` only
controls the Role's explicit deployment during this run. It requires an exact
existing commit and production readiness, reuses matching successful deployments,
waits for matching pending work, and promotes a historical match if it is no
longer active. Matching compares the effective five supported build settings;
a changed setting requires a new deployment. Failed work requires explicit retry.

On failure or timeout, created resources remain for inspection/resumption. The
Role does not automatically roll back or delete resources. Custom domains and
application scaffolding are outside the Project Role. Application environment
variables are owned by `madebyphunky.vercel.env` (production target only).

## Check mode and results

Check mode never invokes npx, because doing so may retrieve/cache a package even
for an API read. It makes a conservative plan with `inspection_limited: true`
and explains that actual provider state was not inspected. It never installs
prerequisites or mutates cloud state. `changed: true` in this mode means work may
be needed, not a claim that observed provider state differs.

The public `vercel_project_result` fact has `project`, `repository`, `deployment`,
`actions`, and `inspection_limited` keys. Resource values are null until known.
Project contains `id`, `name`, `account_id`, and supported `settings`; repository
contains `id`, `full_name`, `url`, `private`; deployment contains `id`, HTTPS `url`,
`state`, requested `sha`, and `active`. Actions record resource creation, linking,
settings updates, deployment creation, or promotion. Failures expose sanitized
partial results and sanitized provider build reasons before failing; preserve
these identifiers for inspection.

Local Vercel/GitHub acceptance passed on 2026-11-02, including exact-commit
deployment, historical production promotion, idempotence, and verified cleanup.
See the repository live-verification guide for evidence and protected CI setup.
