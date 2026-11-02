# Vercel and GitHub live acceptance

The `vercel` Molecule scenario invokes the installed public
`madebyphunky.vercel.project` Role and observes real provider state. It is a
protected, manually triggered readiness gate; local acceptance passed on
2026-11-02 as recorded below. Credential-free harness tests establish cleanup identity guards,
not provider acceptance.

## Required protected configuration

Use a dedicated Vercel test account/team and a GitHub owner configured for disposable
private repositories. Configure the protected GitHub Actions environment `vercel-github-test` with:

| Kind | Name | Meaning |
| --- | --- | --- |
| Secret | `VERCEL_TOKEN` | Token permitted to inspect/create/configure/deploy/delete Projects in the test scope. |
| Secret | `GH_TOKEN` | Token permitted to inspect/create private repositories, write test application contents, and delete those exact repositories. |
| Variable | `VERCEL_TEST_SCOPE_TYPE` | `personal` or `team`. |
| Variable | `VERCEL_TEST_SCOPE_ID` | Explicit Vercel user/account or team ID. |
| Variable | `GITHUB_TEST_OWNER` | Explicit GitHub username or organization owning disposable repositories. |

The Vercel GitHub App must already have access to repositories created by the test.
An installation restricted to selected existing repositories may not include newly
created ones. Resolve App authorization before running acceptance; neither token
alone grants that authorization. GitHub Actions' ordinary repository token should
not be assumed to grant repository creation or deletion. Configure required
reviewers and trusted deployment branches on the protected environment.

## Install and run

Install the Node.js, GitHub, and Vercel Collections and their declared dependencies
using the repository installation instructions. Supply the protected environment
values through a secret manager, then run from the repository root:

```sh
MOLECULE_GLOB='extensions/molecule/*/molecule.yml' molecule test -s vercel
```

The scenario creates uniquely named empty/sentinel Projects and a main Project
linked to a newly created private empty repository. The main Project is converged
through Ansible directly so Molecule's idempotence stage observes actual Role
change reporting. The verifier exercises the existing-repository mode too.

Fixture code seeds minimal HTML commits through GitHub's content API. This is test
setup, not application scaffolding performed by the Role. The verifier checks
Project settings and preservation of omitted settings, check mode without provider
mutation, exact-commit production deployments, unchanged repeat runs, deployment of
a second commit, historical Deployment reuse/promotion back to the first commit,
and sentinel preservation. It checks actual production target IDs and Git source
SHAs as well as the public Role result.

## Manifests and cleanup

The manifest defaults to `.cache/vercel-live/run.json`, outside Molecule's ephemeral
directory so error handling/pruning cannot discard recovery information. Override
`VERCEL_TEST_MANIFEST` with a unique path for parallel local runs; reruns refuse to
overwrite an existing manifest.

Before mutations, the harness verifies explicit account identity and absence of
all exact allocated names. It records those names before creation, captures provider
IDs after each public Role call (including failures), and verifies account, creation
time, and ID continuity before accepting resource ownership. Cleanup rechecks IDs
and deletes only exact test-created Projects/repository; it never deletes by prefix
or listing an account. The manifest is removed only after absence is confirmed.
Deletion failures retain the manifest for recovery and still attempt other known
resource deletions where safe.

Always run cleanup after a failed or interrupted scenario:

```sh
MOLECULE_GLOB='extensions/molecule/*/molecule.yml' molecule cleanup -s vercel
```

The protected workflow should include an `always()` cleanup step and preserve the
nonsecret manifest as an artifact on failure. A forcibly terminated/lost runner
cannot guarantee cleanup; use its retained exact identity manifest for recovery.
If an ID mismatch or pre-existing resource is detected, the harness refuses deletion
rather than adopting it. Inspect the manifest and provider state before recovery.

## Evidence and limits

A passing live run must include final cleanup and be recorded separately from
local offline checks. Missing credentials, owner permissions, GitHub App access,
or a provider-side build failure leave live acceptance pending. The latest Vercel
package is intentionally selected through npx, so provider compatibility must be
verified by this scenario rather than assumed from a pinned CLI version.

## Recorded local acceptance: 2026-11-02

The full `vercel` Molecule scenario passed against the installed Collections in
the caller-selected madebyphunky Vercel team and GitHub organization. The run used
Ansible Core 2.18.20, Node.js 22.23.4, GitHub CLI 2.103.3, and the actual latest
Vercel CLI 65.9.0 selected through npx.

Passed: empty Projects, private empty repository creation and linking, unchanged
Molecule idempotence, existing-repository reuse, settings preservation, mutation-free
check mode, exact-commit production readiness, unchanged repeat deployment, a second
production commit, and reusing/promoting the historical first Deployment without
rebuilding it. Sentinel preservation and final exact-ID cleanup passed; an extra
cleanup invocation also succeeded. No test resources or recovery manifest remained.

The fixture stores its HTML under `public/`, matching the static output expected
by Vercel. An earlier fixture failure exposed missing build-output diagnostics;
the Role now returns the provider's sanitized build reason and partial resource
identifiers on failure.

For this local run, GH_TOKEN was supplied in process memory from the caller's
authenticated GitHub CLI after its repo/delete_repo scopes were approved. No
separate GitHub PAT was created or committed. Protected CI requires its own
configured secret and environment; this evidence is a local run.
