# madebyphunky.application

Thin Application Collection that composes provider Collections for GitHub,
Vercel, and Supabase setup (ADR-0002). Provider API logic stays in
`madebyphunky.vercel` and `madebyphunky.supabase`.

| Role / playbook | Inputs | Public result |
| --- | --- | --- |
| `madebyphunky.application.local_env` | `application_workdir`, `application_env`, optional `application_env_file` | `application_local_env_result` |
| `playbooks/setup.yml` | Provider Project vars + optional `application_workdir`, `supabase_auth_config`, `vercel_git_sha` | Composes provider Role results |

## Setup playbook

`ansible-playbook madebyphunky.application.setup` (installed playbook path
`playbooks/setup.yml`) is phased and re-runnable:

1. Vercel Project + GitHub link (`ensure` or `existing`) and Supabase Project
2. Migrations when `application_workdir/supabase/migrations` exists
3. Auth when `supabase_auth_config` exists
4. Env wiring (credentials → Vercel production + local `.env.local`) when
   `application_workdir` exists
5. Production Deployment when `vercel_deploy=true` and `vercel_git_sha` is an
   exact 40-character SHA
6. Auth Site URL + localhost redirects when a Deployment URL is known

Missing later stages print what is still needed and do not fail earlier success.

Human prerequisites: provider tokens and Vercel’s GitHub App access to the
repository. See `docs/design/project-creation.md`.

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
