# Supabase Roles: first-version design

This records the grill-with-docs decisions and the user's instruction to implement
remaining details by following the Supabase CLI.

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
- Creation requires a region. Supplied region mismatches fail on existing Projects.
- Generate a random initial database password for new Projects, return it as a
  sensitive fact, and tell the caller to change it afterward. This supersedes the
  earlier caller-supplied creation-password proposal.
- The user selected generated-password CLI creation rather than the proposed API
  exception: the generated password briefly appears in CLI process arguments,
  while logs and nonsecret results omit it. Other credentials use the environment.
- Never rename, move, rotate passwords, delete, recreate, or automatically retry
  indeterminate creation. Existing Projects require no creation password.
- Retain CLI defaults for unexposed creation options. Wait for `ACTIVE_HEALTHY`
  within a configurable 900-second budget, polling every five seconds by default.
- Preserve nonsecret identities when known and the generated password separately
  on partial failure. No rollback. Return ref, organization, name, region, status,
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

## Verification

- Check mode validates local inputs and reports inspection limitations without
  executing the CLI, downloading packages, installing prerequisites, or mutating
  the provider. Remote change reporting is a conservative plan.
- Installed public-Role tests exercise a stateful CLI boundary without credentials.
- Live provider acceptance is separate and has not been run for this first version.

## CLI contract sources

Contracts were checked against official v3.0.0 source, including
[project creation](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/command-internal/project-create-core.ts),
[config diff](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/commands/config/diff/diff.format.ts),
[Auth secret comparison](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/commands/config/push/push.secrets.ts),
and [database push](https://github.com/supabase/cli/blob/v3.0.0/apps/cli/src/command-internal/db-push-core.ts).
