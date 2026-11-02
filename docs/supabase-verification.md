# Supabase first-version verification

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

Live acceptance has not been run. Before treating the Roles as live-ready:

1. Select an explicit disposable Supabase organization with appropriate capacity
   and provide a scoped access token through the environment or protected variables.
2. Create a uniquely named Project in an explicit region, supplying
   `supabase_project_password` from a secret source. Capture its exact ref and verify
   the password is absent from verbose output and all result facts.
3. Re-run the project Role and verify no additional Project or change is reported.
4. Apply a site URL/redirect configuration, repeat without changes, and verify
   omitted Auth fields remain unchanged. Exercise a declared SMTP/OAuth secret
   against a provider configuration suitable for the disposable Project.
5. Apply a versioned migration, rerun with zero changes, and test a history conflict.
   Check that application files and CLI link state are unchanged.
6. Supply a different `supabase_project_password` on a repeat project run and verify
   the Project password remains unchanged. Migrations must still use the original
   current password through `SUPABASE_DB_PASSWORD`.
7. Clean up only the exact Project created for the test, using the provider's tools.
   Deletion is deliberately outside these Roles.

Never put credentials, initial passwords, application secrets, or raw provider
output into committed test evidence. A skipped live run does not count as passing.
