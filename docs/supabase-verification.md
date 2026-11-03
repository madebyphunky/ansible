# Supabase feature verification

Feature specification: [#13](https://github.com/madebyphunky/ansible/issues/13).

Installed public-Role contract tests are in `tests/test_supabase_role.py`.
The stateful CLI double uses official v3.0.0 JSON schemas and checks explicit
remote targeting, environment isolation, Auth ownership, migration-only flags,
password redaction, idempotency, and partial failure behavior.

Run locally:

```sh
python scripts/collection_tools.py install
pytest -q tests/test_supabase_role.py
ansible-lint
black --check tests scripts collections
```

A credential-free smoke check against actual `supabase@latest` on 2026-11-02
returned v3.0.0 and confirmed the `config diff` and `db push` command flags.
This checks command availability, not hosted service behavior.

## Required live acceptance delivery

Follow the existing Gandi/Vercel pattern: a separate Molecule scenario and a
manually triggered workflow backed by a protected GitHub Actions environment.
These are acceptance requirements for the complete hosted Supabase feature.

Implemented delivery:

- Molecule scenario: `extensions/molecule/supabase`
- Acceptance script: `tests/live_supabase_acceptance.py`
- Credential-free cleanup guards: `tests/test_live_supabase_harness.py`
- Protected workflow: `.github/workflows/live-supabase.yml` (`workflow_dispatch`,
  environment `supabase-test`, concurrency group `supabase-acceptance`,
  `always()` cleanup, failure manifest artifact)

Live provider acceptance has not been run yet; the feature is not live-ready
until a successful protected run including verified cleanup is recorded.

### Protected configuration

| Kind | Name | Meaning |
| --- | --- | --- |
| Secret | `SUPABASE_ACCESS_TOKEN` | Token permitted to inspect/create/configure/delete Projects in the disposable Organization. |
| Secret | `SUPABASE_TEST_PASSWORD` | Creation password passed as `supabase_project_password` and reused as `SUPABASE_DB_PASSWORD`. |
| Secret | `SUPABASE_TEST_SMTP_PASS` | Optional disposable SMTP password for declared Auth secret coverage. |
| Variable | `SUPABASE_TEST_ORGANIZATION` | Explicit disposable Organization id or slug. |
| Variable | `SUPABASE_TEST_REGION` | Explicit creation region. |

```sh
MOLECULE_GLOB='extensions/molecule/*/molecule.yml' molecule test -s supabase
MOLECULE_GLOB='extensions/molecule/*/molecule.yml' molecule cleanup -s supabase
```

The scenario must invoke the installed public Roles, observe real provider state,
and include Molecule idempotence. Ordinary PR jobs remain credential-free. Reuse
the prior scenarios' prepare/converge/idempotence/verify/cleanup structure; retry
cleanup with `always()` in CI. Configure environment reviewers and trusted branches
in repository settings as well as referencing the environment in workflow YAML.
Use a provider concurrency group with cancellation disabled to avoid interrupting
cleanup.

Outside the live workflow, callers must serialize creation for the same
Organization/name and subsequent writes to the same Project. V1 does not provide
distributed locking or guarantee atomic creation across controllers.

The protected configuration must supply a scoped access token, an explicit
disposable Organization and region, and a creation password from a secret source.
The harness passes the password explicitly as `supabase_project_password` and uses
it as `SUPABASE_DB_PASSWORD` for migrations. The project Role itself has no password
environment fallback. Any SMTP/OAuth fixture needed to exercise a declared Auth
secret must be configured explicitly; unavailable prerequisites leave acceptance
pending rather than silently reducing the claimed coverage.

## Required live cases

1. Verify the selected Organization and capacity, allocate unique exact Project
   names, prove initial absence, and persist a nonsecret ownership manifest before
   creation. Keep it outside Molecule's ephemeral directory and refuse overwrite.
2. Create a disposable Project in the explicit region with the supplied password.
   Capture the exact project reference, verify readiness and returned identity,
   and prove credentials are absent from verbose output and all result facts.
3. Re-run the project Role and verify no additional Project or change is reported.
   Exercise existing-resource adoption with explicit reference and organization.
4. Apply Auth site URL/redirect settings, repeat with zero changes, and observe
   omitted-field preservation through provider reads. Exercise a declared Auth
   secret using the configured disposable fixture; do not claim email delivery or
   end-user OAuth login from a configuration-only test.
5. Apply a versioned SQL migration, verify its database effect, repeat with zero
   changes, and test a history conflict without automatic repair. Prove application
   files and CLI link state remain unchanged.
6. Supply a different `supabase_project_password` on a repeat project run and prove
   the database password remains unchanged. Migrations must still connect using
   the original current password through `SUPABASE_DB_PASSWORD`.
7. Exercise check mode and confirm provider state remains unchanged. Verify an
   unrelated sentinel resource/configuration remains untouched throughout.
8. Clean up only exact test-created Project references. Verify Organization,
   initial-absence proof, creation identity, and reference continuity before
   deletion. Never delete a pre-existing, ambiguous, or mismatched resource.
   Cleanup does not add deletion to the public Roles.

## Cleanup, failure, and evidence

Capture exact identities after public Role calls, including partial failures. If
creation is indeterminate, reconcile using the persisted pre-creation evidence
and provider identity; fail closed when ownership cannot be established. A name
match or prefix alone is not deletion authority.

Persist pre-creation absence evidence and the exact reference returned by a
confirmed creation call before inspecting provider state. Both prepare and the
converge playbook retain these creation receipts; converge does so even when a
later Role task fails. A matching receipt plus initial absence, Organization,
name, and reference continuity establishes ownership independently of the
provider timestamp. The first live attempt exposed a returned creation timestamp
roughly 117 minutes before the run, so timestamp recency alone cannot establish
ownership for every newly allocated Project. Without a receipt, the conservative
timestamp guard remains; legacy failed manifests may require explicit operator
recovery rather than automatic deletion.

Attempt cleanup after both successful and failed tests. Remove the manifest only
when provider absence is confirmed; otherwise retain it for safe recovery and
upload the nonsecret manifest as a failure artifact. A lost runner cannot guarantee
cleanup. Add credential-free harness tests proving rejection of pre-existing or
mismatched identities, safe failure recovery, and manifest retention on cleanup
failure.

A successful live run including final cleanup is a readiness gate, following the
previous provider features. Record dated versions, scope, cases, and limitations;
distinguish local execution from protected-CI execution. Contract tests and CLI
help/version smoke checks are separate evidence and do not satisfy this gate.
Identify the tested commit and actual resolved CLI version. Before readiness,
rerun acceptance after relevant Role behaviour changes or a CLI upgrade so that
the recorded evidence covers the version being delivered.
Missing credentials, fixtures, capacity, provider failures, or unverified cleanup
leave acceptance pending.

Never commit credentials, passwords, application secrets, or raw provider output
as test evidence. A skipped live run does not count as passing.
