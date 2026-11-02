# dns_gandi_livedns

Run `madebyphunky.infra.dns_gandi_livedns` to manage explicit Gandi LiveDNS RRsets
in a zone already controlled by the caller. The Role uses
`community.general.gandi_livedns`, not zone-wide HTTP replacement operations.

## Inputs

| Variable | Required | Meaning |
| --- | --- | --- |
| `gandi_livedns_zone` | Yes | One zone, without a trailing dot. |
| `gandi_livedns_records` | Yes | Nonempty list of explicit RRsets. |
| `gandi_livedns_personal_access_token` | Unless environment supplies it | Gandi PAT; takes precedence over `GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN`. |

An explicitly supplied blank token fails instead of falling back to the
environment. No legacy API-key authentication is supported. The token is marked
`no_log` in the argument specification and credential-bearing tasks.

| Record field | Meaning |
| --- | --- |
| `name` | Required relative name, such as `www`, `nested.www`, `_acme-challenge`, or `*.preview`; `@` means apex. |
| `type` | Required uppercase type, such as `A`, `AAAA`, `CNAME`, `MX`, or `TXT`. |
| `state` | `present` (default) or `absent`. |
| `ttl` | Explicit integer seconds, required for `present`; no TTL default. |
| `values` | Nonempty list of strings, required for `present`; complete values of the RRset in provider format. |

Names with a trailing dot or the full zone suffix are rejected. Names differing
only in case are treated as the same identity for duplicate detection. Use one
entry per name/type. Unknown record fields are rejected to catch misspellings.
Present TTLs must be integers (not quoted numbers); values must be strings.
Provider-specific content validity, including supported types and TTL ranges,
remains with Gandi and the module. Values are never automatically quoted,
expanded, or converted. In particular, supply TXT quoting and MX priorities in
the format Gandi expects.

## Behaviour

The entire batch is validated before any mutation. Missing or empty input,
duplicates even when identical, invalid states, missing required fields, invalid
names, and invalid present content fail before provider calls.

Every entry owns all values for `(zone, name, type)`. A present entry replaces the
complete value list and TTL. An absent entry deletes the complete RRset, even if
TTL or values were supplied; prefer deletion entries with just name, type, state.
Omitting a declaration leaves existing DNS records untouched. There is no prefix
inference, ownership marker, pruning, or saved ownership history.

Entries run in input order. The first API failure stops execution before the next
entry. Completed changes remain; there is no rollback or automatic retry. After
correcting a failure, rerun the desired input to converge. Input validation does
not guarantee Gandi will accept every declaration; a provider content error may
still cause partial progress. Callers must ensure a single owner per RRset.

Check mode predicts changes without applying them. A second identical run after
convergence reports no changes. API execution is redacted to protect the PAT;
validation messages and task names provide context without disclosing it.

See the [Collection guide](../../README.md) for installation and execution and
[live verification](../../docs/live-verification.md) for acceptance requirements.
