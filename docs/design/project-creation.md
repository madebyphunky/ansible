# Project creation

Requirements confirmed during the project-creation design interview. This is a
design in progress, not an implementation specification.

## Confirmed requirements

- Support replacing Lovable with an Agent-driven workflow.
- Use GitHub for application source, Vercel for the frontend, and Supabase for
  the backend.
- Support starting from an idea with no codebase and starting from an existing
  codebase. A template repository cannot be a required starting point.
- Initially support local development and production. Keep Vercel previews
  disabled until database isolation is configured; isolated previews are deferred.
- Provider accounts and credentials are prerequisites. Account registration and
  billing happen once, outside this flow. Roles create repositories and Projects
  inside already-authenticated accounts.
- Application code is authored or adapted by a coding Agent. A later milestone
  may let a prompt create code and then deploy it; scaffolding is not Role scope.
- From-scratch creates an empty private GitHub repository. Adoption requires an
  existing GitHub repository and links Vercel to it.
- Vercel and Supabase Projects use existing ensure semantics: reuse an exact name
  match, create when absent, fail when ambiguous.
- Package a thin Application Collection that depends on `madebyphunky.vercel` and
  `madebyphunky.supabase`. It owns the composer playbook only; provider API logic
  stays in provider Collections. See ADR-0002.
- The playbook is phased and re-runnable. A from-scratch first run creates the
  empty GitHub repository, Vercel Project, and Supabase Project, then stops
  cleanly until application source, Auth `config.toml`, and migrations exist.
  Re-running continues through later stages.
- Add Roles to retrieve the Supabase Project URL and publishable key, set the
  corresponding Vercel Project environment variables for production, and write
  local development equivalents for the Agent.
- Publishable values may go to Vercel production and local client env. The secret
  key may go only to non-public Vercel server env and a local secret file that is
  never committed—never to `NEXT_PUBLIC_*` or source control.
- After the first production Deployment URL exists, Auth sets Site URL to that
  URL and allows redirects for that origin plus localhost. First pass may skip
  Auth URL updates until a Deployment URL is known; re-run applies them.
- After source exists, compose reusable Roles in this order: migrations → Auth →
  env wiring (local + production) → production Deployment of an exact git SHA.
  Ordering lives in the playbook; each step remains an independently reusable
  Role.

## Open decisions

- How the playbook decides a stage is ready to run vs stop cleanly.
- Environment variable naming contract (framework-specific defaults vs caller map).
- Who supplies the exact git SHA for Deployment, and which one-time human
  prerequisites remain outside Roles.
