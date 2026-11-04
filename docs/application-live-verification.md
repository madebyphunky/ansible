# Application setup live verification

Feature specification: [#15](https://github.com/madebyphunky/ansible/issues/15) /
verification ticket [#19](https://github.com/madebyphunky/ansible/issues/19).

Design source of truth: [`docs/design/project-creation.md`](design/project-creation.md).
Credential-free composer contracts: `tests/test_application_setup_playbook.py`.

The Application setup path composes installed public Roles from
`madebyphunky.vercel`, `madebyphunky.supabase`, and `madebyphunky.application`
through `playbooks/setup.yml`. Live acceptance is a protected, manually
triggered readiness gate for that multi-provider path. Ordinary PR jobs remain
credential-free. Missing credentials, fixtures, provider failures, or unverified
cleanup leave acceptance **pending**—never pass.

Follow the same honesty standard as
[Supabase verification](supabase-verification.md) and
[Vercel live verification](vercel-live-verification.md).

## Required protected configuration

Use disposable Vercel and Supabase test scopes plus a GitHub owner configured for
disposable private repositories. A dedicated protected GitHub Actions environment
(for example `application-setup-test`) must supply:

| Kind | Name | Meaning |
| --- | --- | --- |
| Secret | `VERCEL_TOKEN` | Token permitted to inspect/create/configure/deploy/delete Projects in the test scope. |
| Secret | `GH_TOKEN` | Token permitted to inspect/create private repositories, write fixture contents, and delete those exact repositories. |
| Secret | `SUPABASE_ACCESS_TOKEN` | Token permitted to inspect/create/configure/delete Projects in the disposable Organization. |
| Secret | `SUPABASE_TEST_PASSWORD` | Creation password for the disposable Supabase Project (`supabase_project_password` / `SUPABASE_DB_PASSWORD`). |
| Variable | `VERCEL_TEST_SCOPE_TYPE` | `personal` or `team`. |
| Variable | `VERCEL_TEST_SCOPE_ID` | Explicit Vercel user/account or team ID. |
| Variable | `GITHUB_TEST_OWNER` | Explicit GitHub username or organization owning disposable repositories. |
| Variable | `SUPABASE_TEST_ORGANIZATION` | Explicit disposable Organization id or slug. |
| Variable | `SUPABASE_TEST_REGION` | Explicit creation region. |

The Vercel GitHub App must already have access to repositories created by the
test. Configure environment reviewers and trusted branches in repository
settings. Use a provider concurrency group with cancellation disabled so cleanup
is not interrupted. Do not expose these credentials to ordinary PR checks.

## Required live cases

1. **Infrastructure-only first run.** With no `application_workdir`,
   `application_auth_config`, or `vercel_git_sha`, ensure an empty private GitHub
   repository (or adopt an existing one), linked Vercel Project without a
   Deployment, and ready Supabase Project. Later stages must skip cleanly with
   messages naming what is still needed; earlier stages remain successful.
2. **Re-run with migrations, Auth, and env wiring.** After Application source
   exists, supply `application_workdir` (with `supabase/migrations`) and
   `application_auth_config`. Apply pending migrations, Auth from the declared
   config, production Vercel env vars, and gitignored local `.env.local`. Prove
   publishable values reach production + local client env and the secret key
   reaches only non-public Vercel server env and `.env.local`.
3. **Production Deployment and Auth URL update.** Supply an exact 40-character
   `vercel_git_sha` after push. Publish that commit as the production Deployment,
   then update Auth Site URL to the Deployment origin and allow that origin plus
   localhost redirects. Do not set play-level `vercel_deploy` or
   `supabase_auth_config` (composer-owned stage inputs).
4. **Secret redaction.** Verbose output and public result facts must not contain
   access tokens, creation passwords, or the Supabase secret key. Contract tests
   cover the credential-free analogue; live runs must confirm the same.
5. **Cleanup ownership rules.** Persist a nonsecret ownership manifest with exact
   identities (Vercel Project id, GitHub repository full name/id, Supabase
   project reference) before or immediately after creation. Clean up only those
   exact test-created resources after verifying account/organization, name, and
   identity continuity. Never delete by name prefix, broad listing, or ambiguous
   match. Retain the manifest when absence cannot be confirmed; upload it as a
   failure artifact. Attempt cleanup after success and failure (`always()` in CI).

## Evidence and limits

A successful live run must include final cleanup and record the tested commit,
resolved CLI/runtime versions, exercised cases, and limitations. Distinguish
local execution from protected-CI execution. Contract tests and CLI help/version
smoke checks do not satisfy this gate.

Scaffolding remains Agent-owned: live fixtures may seed minimal Application
source for migrations/Auth/deploy, but Roles must not author product code.
Preview isolation, custom domains, and the full Marketplace `POSTGRES_*` set
remain out of scope.

## Recorded acceptance

**Pending.** No protected (or local) live Application setup run has been recorded
yet. Until a successful run including verified final cleanup is captured here—
with commit SHA, versions, coverage, and limitations—Application setup live
acceptance remains pending and must not be treated as passing. Missing
credentials or an unconfigured protected environment also leave the gate pending.
