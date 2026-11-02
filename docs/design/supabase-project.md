# Hosted Supabase support: feature specification

Feature specification: [#13](https://github.com/madebyphunky/ansible/issues/13).

This records the grill-with-docs decisions and the user's instruction to implement
remaining details by following the Supabase CLI.

## Feature boundary

The feature is the complete hosted Supabase support delivered by PR #12:
Project provisioning, Auth configuration, database migrations, Collection packaging,
prerequisite composition, example playbooks, documentation, and verification.
Live acceptance is a verification concern within this feature, not a separate
feature. The agreed Role interfaces and behaviour below remain the starting point
for this documentation review.

Follow the same delivery and verification pattern as the Gandi and Vercel features:
credential-free PR checks, a protected manually triggered live Molecule scenario,
and a successful real-provider acceptance run including verified cleanup before
readiness. Document local and protected-CI evidence separately. A manual checklist
or simulated CLI test does not satisfy the live gate.

## Scope and composition

- Hosted Supabase only; self-hosted and local development stacks are outside scope.
- Public Roles: `madebyphunky.supabase.project`, `madebyphunky.supabase.auth`, and
  `madebyphunky.supabase.migrations`, in the independently installable
  `madebyphunky.supabase` Collection.
- Each Role is independently runnable with explicit inputs. Thin example playbooks
  compose them, passing the project reference from the project Role.
- Storage buckets, Edge Functions, and function secrets are outside this delivery.

## CLI execution

- Use `npx --yes supabase@latest`, with `supabase_cli_version` as an override.
- CLI v3 is the initial supported contract; follow its configuration and migration
  semantics. Fail clearly on incompatible structured responses.
- Compose the existing Node.js setup Role, optionally disabled for caller-managed
  prerequisites. Validate local inputs before prerequisite changes.
- Use isolated temporary workdirs and CLI home, explicit remote references, and
  explicit credentials. Do not use saved login or link state.
- Remove ambient `SUPABASE_*` overlays except the selected credentials and isolated
  CLI home. Other environment variables remain available to Auth `env(NAME)`.

## Project identity and lifecycle

- Require an explicit organization and exact Project name. Resolve organization
  IDs/slugs through the CLI's organization listing and pass the resolved slug.
- Optional project reference must resolve to an existing Project matching the
  supplied organization and name.
- Without a reference, exact organization/name lookup reuses one match, creates on
  zero matches, and fails on multiple matches.
- Callers serialize creation for the same Organization/name and subsequent writes
  to the same Project. V1 provides no distributed lock or cross-controller atomic
  creation guarantee; the live workflow's concurrency group protects only its own
  test runs.
- Creation requires a region. Supplied region mismatches fail on existing Projects.
- Require an explicit `supabase_project_password` Role input when creating a new
  Project. There is no password generation or environment fallback for this input.
- The CLI requires the creation password in process arguments. Mark it no_log,
  suppress provider output that could echo it, and never return it in result facts.
  Other credentials use the child environment.
- Never rename, move, rotate passwords, delete, recreate, or automatically retry
  indeterminate creation. Existing Projects require no creation password.
- Retain CLI defaults for unexposed creation options. Wait for `ACTIVE_HEALTHY`
  within a configurable 900-second budget, polling every five seconds by default.
- Preserve nonsecret identities when known on partial failure; never return
  passwords. No rollback. Return ref, organization, name, region, status,
  and project URL; do not retrieve API keys or connection strings.

## Auth

- Follow the CLI-supported Auth configuration surface, including SMTP/OAuth;
  do not impose a smaller field whitelist.
- Accept a Supabase config.toml, stage only its declared Auth tree, and preserve
  omitted remote fields. Explicit empty lists clear those lists.
- Use structured config diff/push responses. Remote-only differences are preserved;
  declared secrets use CLI push's digest comparison rather than blind writes.
- Fail on unsupported, unavailable, gated, or unapplied requested configuration.
- Never modify the caller's config file or apply unrelated config sections.

## Migrations

- Use the existing checkout's `supabase/migrations`, staged in an isolated workdir.
- Use CLI db push dry-run followed by pending-only push against an explicit remote.
  Pass the current DB password through `SUPABASE_DB_PASSWORD`.
- No automatic reset, history repair, rollback, seeds, roles, Vault secret updates,
  or include-all. Fail on history conflicts using CLI behavior.
- Migration authors own SQL, including destructive statements. Reconciliation uses
  CLI migration versions, not checksums of already-applied files.
- Do not modify or link the application checkout.

## Acceptance criteria

These criteria apply to the entire feature, not just individual Role task files.

### Public behaviour and delivery

- Build and install the independently packaged Collection with declared sibling
  dependencies through the repository tooling.
- Provide argument specifications, defaults, documented credentials/results,
  installation instructions, and a thin example composing all three public Roles.
- Support the repository's Ansible Core 2.18/2.19 matrix and supported macOS and
  Ubuntu/Debian prerequisite paths; reuse the existing Node.js setup Role.
- Exercise installed public Roles as the primary test seam. Prove validation,
  explicit organization/project identity, supplied-password handling, omission
  preservation, idempotency, failure reporting, and unchanged application files.
- Check mode validates local inputs and reports inspection limitations without
  executing the CLI, downloading packages, installing prerequisites, or mutating
  the provider. Remote change reporting is a conservative plan.
- Ordinary PR checks remain credential-free and pass lint, formatting, packaging,
  supported-version contracts, and the existing provider suites.

### Live acceptance

- Add a separate `supabase` Molecule scenario invoking the actual installed
  `project`, `auth`, and `migrations` Roles against a disposable Supabase Organization.
- Add a manually triggered GitHub Actions workflow using a protected environment
  and explicit scoped credentials/configuration, following Gandi/Vercel. Do not
  expose provider credentials to ordinary PR checks.
- Verify creation, exact-identity adoption, readiness, repeat-run idempotency,
  Auth changes and omitted-field preservation, pending migrations and history
  conflicts, password redaction, no implicit password rotation, check-mode safety,
  and preservation of unrelated resources and application/link state.
- Use uniquely named disposable Projects. Persist a nonsecret recovery manifest
  before creation, capture exact provider references including partial failures,
  and verify ownership before cleanup. Never delete by name prefix or broad scope.
- Cleanup is test-harness functionality, not a new destructive public Role feature.
  Attempt cleanup on success and failure; confirm absence before removing the
  manifest. Retain recovery information and upload it on workflow failure.
- Add credential-free harness tests for ownership guards and cleanup/failure paths.
- Record a successful live run, including final cleanup, CLI/runtime versions,
  exercised cases, and limitations. Missing credentials, capacity, required Auth
  fixtures, provider failures, or failed cleanup leave the gate pending.
- Identify the tested commit and resolved CLI version in live evidence. Before
  readiness, rerun acceptance after relevant behaviour changes or a CLI upgrade;
  evidence for older behaviour or a different CLI does not validate the delivery.
- Keep local evidence distinct from protected-CI evidence. No skipped run counts
  as a successful live run.

### Current gaps

The public Roles, packaging, examples, documentation, and simulated CLI contract
suite exist. The executable Supabase Molecule scenario, protected live workflow,
cleanup harness/tests, and successful hosted acceptance evidence are missing.
Supported-version CI failures must also be resolved before feature readiness.
The implementation review also requires exact Project-reference validation with
realistic fixtures, staging files referenced by Auth email-template/notification
`content_path` settings, and correcting compatibility documentation that promises
incompatible responses are always detected before mutation. Some response failures
can only be detected after a create/push, so partial-mutation reporting and recovery
must remain explicit.
See `docs/supabase-verification.md` for the required acceptance procedure.

## CLI contract sources

Contracts were checked against official v3.0.0 source, including
[project creation](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/command-internal/project-create-core.ts),
[config diff](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/commands/config/diff/diff.format.ts),
[Auth secret comparison](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/commands/config/push/push.secrets.ts),
and [database push](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/command-internal/db-push-core.ts).
