# Vercel and GitHub live acceptance

The `vercel` Molecule scenario invokes the installed public
`madebyphunky.vercel.project` Role and observes real provider state. It is a
protected, manually triggered readiness gate; no Vercel/GitHub live run has been
claimed yet. Credential-free harness tests establish cleanup identity guards,
not provider acceptance.

## Required protected configuration

Use a dedicated Vercel test account/team and a GitHub owner configured for disposable
private repositories. Configure the protected workflow environment with:

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
