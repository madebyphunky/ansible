# madebyphunky.application

Thin Application Collection that composes provider Collections for GitHub,
Vercel, and Supabase setup (ADR-0002). Provider API logic stays in
`madebyphunky.vercel` and `madebyphunky.supabase`.

| Role / playbook | Inputs | Public result |
| --- | --- | --- |
| `madebyphunky.application.local_env` | `application_workdir`, `application_env`, optional `application_env_file` | `application_local_env_result` |
| `playbooks/setup.yml` | Provider Project vars + optional `application_workdir`, `application_auth_config`, `application_env_names`, `vercel_git_sha` | Composes provider Role results |

## Setup playbook

`ansible-playbook madebyphunky.application.setup` (installed playbook path
`playbooks/setup.yml`) is phased and re-runnable:

1. Vercel Project + GitHub link (`ensure` or `existing`) and Supabase Project
2. Migrations when `application_workdir/supabase/migrations` exists
3. Auth when `application_auth_config` exists
4. Env wiring (credentials → Vercel production + local `.env.local`) when
   `application_workdir` exists
5. Production Deployment when `vercel_git_sha` is an exact 40-character SHA
6. Auth Site URL + localhost redirects when a Deployment URL is known

Missing later stages print what is still needed and do not fail earlier success.
Do not set play-level `vercel_deploy`, `supabase_auth_config`, or
`application_env` (including false/empty values); those Role
inputs are stage-local and Ansible extra-vars would override the composer. Supply
`vercel_git_sha` when the exact commit is ready, and `application_auth_config`
for the declared Auth config.toml.

Human prerequisites: provider tokens and Vercel’s GitHub App access to the
repository. Design source of truth: `docs/design/project-creation.md`. Live
verification expectations: `docs/application-live-verification.md`.

## Local environment file

`madebyphunky.application.local_env` writes mapped values to `.env.local` (override
with `application_env_file`) inside `application_workdir`. It refuses to write
unless `git check-ignore` reports the path as ignored. Secrets must never be
committed; do not debug `application_env`.

Documented default names for Supabase + Next.js:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`

Install sibling Collections with `python scripts/collection_tools.py install`
from the repository root.

## Supabase environment names

The setup playbook retrieves values from Supabase and sends the same values to
Vercel production and the local file. Rename them with a partial
`application_env_names` map:

```yaml
application_env_names:
  url: PUBLIC_SUPABASE_URL
  publishable_key: PUBLIC_SUPABASE_KEY
  secret_key: SUPABASE_SERVER_KEY
```

Omitted entries retain the defaults above. Names must be distinct environment
identifiers. Keep the secret name server-only: common client prefixes
(`NEXT_PUBLIC_`, `PUBLIC_`, `VITE_`, `REACT_APP_`, `NUXT_PUBLIC_`) are refused;
callers must also follow their framework's exposure rules. The standalone
`local_env` Role still accepts `application_env` values directly.

## Optional Kamal server preparation

`madebyphunky.application.kamal_setup` is a separate thin composer for an existing
VPS; it does not run the Vercel/Supabase setup flow. Run it with:

```sh
ansible-playbook madebyphunky.application.kamal_setup -e @kamal-vars.yml
```

Supply the `kamal_*` inputs documented in the Kamal Collection. Omit
`application_kamal_dns_provider` for server preparation alone, or set it to
`gandi` or `spaceship` and supply that provider Role's ordinary zone, explicit
record sets, and credentials. The selected DNS Role runs before server setup;
its failure stops the play. Check mode predicts DNS and Docker changes without
mutating either. CI owns all Application deployments, including the first.
