# LiveDNS acceptance

The live Molecule scenario tests the installed public Role against actual Gandi
LiveDNS. It uses API reads, so acceptance does not depend on recursive DNS caches.
Use a dedicated test zone, never production. Use a PAT scoped as narrowly as Gandi
permits for that zone, with permission to read and manage its LiveDNS records.

## Protected CI setup

Create a GitHub Actions environment named `gandi-livedns-test`. Configure required
reviewers and restrict deployment branches to trusted code. Environment protection
is a repository setting: checking in the workflow alone does not configure it.

Set environment secret `GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN` and environment
variable `GANDI_LIVEDNS_TEST_ZONE`. Do not put either credential in committed files.
The zone name is configuration rather than a secret. PR checks receive no PAT.

Manually dispatch the **LiveDNS acceptance** workflow on a trusted branch. It
installs the Collection, runs `molecule test -s live`, then attempts cleanup even
when acceptance fails. Concurrency prevents one CI live run cancelling another.
The readiness gate is a successful workflow run, not merely a successful PR job.

## Local run

After installing the development dependencies and the Collection, supply the PAT
and test zone through environment variables and run:

```sh
molecule test -s live
```

The scenario allocates unique names, confirms their A RRsets are initially absent,
and records every exact allocated identity before creating anything. The manifest
contains zone and identities, never credentials. It seeds an unrelated sentinel,
converges two managed record sets, and runs Molecule idempotence. The verifier then
checks complete replacement and TTL changes, check mode without mutation, omission
preservation, explicit deletion, preflight validation before any mutation, and
sentinel preservation. It also injects a test failure and checks cleanup of only
that fixture while other records remain unchanged.

Cleanup attempts each exact allocated RRset independently, verifies absence, and
removes the manifest only after all succeed. There is no zone-wide or prefix-wide
cleanup. The workflow retries cleanup with an `always()` step; Molecule also runs
cleanup after test failures. A forcibly killed runner cannot guarantee cleanup.
Retain the nonsecret run manifest if cleanup is interrupted or fails, and retry:

```sh
molecule cleanup -s live
```

Do not start a new run over an existing manifest. If the runner is lost, inspect
the allocated identities before deleting records manually. Never clean a zone by
matching the test prefix. A successful live run must verify cleanup too.

## Evidence

The credential-free contract suite and syntax/lint checks can run without external
access. Real Gandi acceptance still requires the protected environment, a dedicated
zone, and its PAT; report a missing live run as pending rather than passing.

## Test records under a subdomain

Gandi may expose a parent zone rather than a separate subdomain zone. To keep
all test records under `xyz.markharwood.info`, set `GANDI_LIVEDNS_TEST_ZONE`
to `markharwood.info` and optional `GANDI_LIVEDNS_TEST_NAME_SUFFIX` to `xyz`.
Set the suffix as an environment variable in the protected CI environment too.
The generated relative names then end in `.xyz`; cleanup still uses only the
exact identities saved in the manifest. An empty suffix tests directly in the zone.

## Recorded local acceptance: 2026-11-02

`molecule test -s live` passed against the installed Collection with Ansible Core
2.19.14 and community.general 13.5.0. Gandi exposes `markharwood.info` as the
zone; the run restricted every test identity to relative names ending in `.xyz`,
under the caller-selected `xyz.markharwood.info` subdomain.

Preparation, convergence, Molecule idempotence (zero changes), and the live verifier
all passed. Verification covered replacement of values and TTL, check mode without
mutation, omission and sentinel preservation, rejection of invalid input before
mutation, explicit deletion, and failure-fixture cleanup. Final cleanup verified
absence of all allocated RRsets, and an additional cleanup invocation succeeded.
No PAT is recorded here or in the run manifest. Protected GitHub Actions acceptance
still requires the documented environment configuration; this was a local run.
