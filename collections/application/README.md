# madebyphunky.application

Thin Application Collection that composes provider Collections for GitHub,
Vercel, and Supabase setup (ADR-0002). Provider API logic stays in
`madebyphunky.vercel` and `madebyphunky.supabase`.

| Role | Inputs | Public result |
| --- | --- | --- |
| `madebyphunky.application.local_env` | `application_workdir`, `application_env`, optional `application_env_file` | `application_local_env_result` |

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
