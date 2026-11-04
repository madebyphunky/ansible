# Project creation

Design interview for quick Application setup with GitHub, Vercel, and Supabase.
Not an implementation specification.

## Confirmed requirements

- Replace Lovable with an Agent-driven workflow: GitHub for source, Vercel for
  frontend, Supabase for backend.
- Support from-scratch (no codebase) and adoption of an existing codebase.
  Templates are not required.
- Environments: local development and production first. Isolated previews are
  deferred. “Previews disabled” means production + local Supabase env only (never
  Preview-scoped Vercel env), no Supabase branching, no Role to toggle Vercel’s
  git preview switch. Production publishes via exact-SHA Deployment.
- Provider accounts/credentials are prerequisites. One-time human setup outside
  Roles: provider auth + Vercel GitHub App with access to the target repository.
- Roles do not scaffold application code. The Agent authors or adapts code. A
  later prompt→code→deploy milestone is out of Role scope for now.
- From-scratch: create empty private GitHub repository. Adoption: require an
  existing repository and link Vercel to it.
- Vercel and Supabase Projects use ensure semantics (reuse exact name match,
  create if absent, fail if ambiguous).
- Package `madebyphunky.application` (depends on `madebyphunky.vercel` and
  `madebyphunky.supabase`) as a thin composer Collection. See ADR-0002.
- New Roles: Supabase key/URL retrieval in `madebyphunky.supabase`; Vercel
  application env management in `madebyphunky.vercel`; local `.env.local` writing
  in `madebyphunky.application` (refuse if path is not gitignored).
- v1 wiring: Project URL + publishable key + secret key only (caller name map;
  defaults `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `SUPABASE_SECRET_KEY`). No full `POSTGRES_*` Marketplace set yet.
- Publishable → Vercel production + local client env. Secret → non-public Vercel
  server env + `.env.local` only—never `NEXT_PUBLIC_*` or source control.
- Phased, re-runnable playbook. Missing later-stage inputs stop that stage cleanly
  and report what’s needed; earlier stages stay successful. Hard fail only inside
  a stage that was ready.
- After source exists, compose reusable Roles: migrations → Auth → env wiring
  (local + production) → production Deployment (Agent-supplied exact git SHA).
- After first production Deployment URL exists, Auth sets Site URL to it and
  allows that origin plus localhost; earlier runs may skip Auth URL updates.
- The setup playbook owns stage-local Role inputs that would break ordering if
  set as play-level extra-vars (`vercel_deploy`, `supabase_auth_config`). Callers
  supply `vercel_git_sha` and `application_auth_config` instead.

## Glossary / ADRs touched

- `GLOSSARY.md`: Application, Infrastructure setup
- `docs/adr/0002-application-collection.md`: Application Collection packaging
