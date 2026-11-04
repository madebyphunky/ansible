# Vercel Project Role: agreed design

This records the grill-with-docs decisions. It is a design handoff, not an
implementation. See the provider-scoped Collections ADR for public naming.

## Collections and prerequisites

- `madebyphunky.vercel.project` manages Vercel Projects.
- `madebyphunky.github.cli` provides the GitHub CLI as a reusable Role.
- `madebyphunky.nodejs.setup` provides Node.js, npm, and npx as a reusable Role.
- Compose prerequisite setup when required. Initially support macOS via Homebrew
  and Ubuntu/Debian via package tooling; fail clearly on unsupported platforms.
- Node.js defaults to an active LTS release and reuses compatible existing runtimes.
- Invoke Vercel through `npx --yes vercel@latest`; do not manage a persistent Vercel
  CLI installation or pin its version. Supply Vercel's own noninteractive options
  separately from npm's installation-prompt suppression.
- Use `gh` for GitHub repository management and Git for Git operations. Vercel CLI
  API access may cover settings and commit-specific deployment operations.
- `madebyphunky.gandi.livedns` manages explicit Gandi LiveDNS record sets.

## Credentials and resource identity

- Ansible variables and environment fallbacks use the identical provider-wide
  names `VERCEL_TOKEN` and `GH_TOKEN`. Explicit Ansible values win.
- Redact credentials and never commit them. No implicit CLI-login identity.
- Require the Vercel Project name and an explicit account/team ID.
- GitHub modes require explicit repository owner and name.
- Vercel GitHub App access is a prerequisite for repository linking; a bearer token
  alone does not establish that access.

## Project and repository behaviour

- Three explicit source modes: no repository, link an existing GitHub repository,
  or ensure a GitHub repository exists and link it.
- Newly created repositories default to private and empty. Application scaffolding
  and repository content creation are outside scope.
- An empty Vercel Project is a valid outcome. Deployment is opt-in and disabled by
  default.
- Reuse matching existing resources. Fail on a Project linked to a different
  repository; never silently relink, overwrite, or delete existing resources.
- Allow optional framework, root directory, build command, install command, and
  output directory settings. Apply supplied settings and preserve unspecified
  settings on existing Projects.
- Linked repositories retain normal Vercel deployments on future Git pushes.
  The deployment option controls the Role's explicit request during a run.
- Custom domains and DNS remain outside the Project Role. Application environment
  variables are owned by `madebyphunky.vercel.env` (production target only; never
  Preview-scoped)—not a Collection-wide exclusion. Application setup composition
  is recorded in `docs/design/project-creation.md`.

## Explicit deployment

- Require an exact existing Git commit SHA. A new empty repository needs code
  before it can be deployed.
- Request production deployment and wait until ready, returning its URL.
- Reuse a successful production Deployment for the SHA when build settings match;
  wait for a matching in-progress deployment instead of creating a duplicate.
- Reusing an older Deployment must make the requested version active in production,
  not merely return a historical URL. With deployment disabled, the Role does not
  explicitly change the active production version.
- Failed deployments fail clearly. Retrying requires an explicit option.
- Wait up to 15 minutes by default, with a configurable timeout. On failure or
  timeout retain created resources and return identifiers for inspection/resumption.
  No automatic rollback or deletion.

## Verification

- Check mode performs no installation or provider mutations. Report planned
  changes; explicitly report inspection limitations when prerequisites are missing.
- Credential-free PR tests cover the public Role contract and repeat-run safety.
- Protected, manually triggered live acceptance is required before readiness.
- Live tests use uniquely named disposable Projects and private repositories,
  verify deployment and idempotency, and clean up only resources created by the run.
