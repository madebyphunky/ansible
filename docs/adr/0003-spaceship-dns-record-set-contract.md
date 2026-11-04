# Spaceship DNS preserves the Gandi record-set contract

Provide `madebyphunky.spaceship.dns` in its own provider Collection for zones
already hosted on Spaceship, excluding registration, transfers, and nameserver
changes. Preserve the Gandi Role's zone and record declarations (`name`, `type`,
`state`, `ttl`, and string `values`) with Spaceship-specific variable names,
covering all record types supported by the Spaceship DNS API. Keeping string
values requires translation into Spaceship's structured record fields, but
preserves the caller's existing declaration model instead of introducing a
second provider-shaped value interface.

Each declaration owns the complete RRset identified by zone, name, and type;
omitted RRsets remain untouched. Validate the entire batch before mutation.
Spaceship's individual-record operations require reading and comparing records,
then adding/updating desired values and deleting stale ones to converge; do not
treat an API upsert as whole-RRset replacement. Conflicting product-managed
records cause failure and are not forcibly modified.

Retain check-mode prediction and unchanged results on an identical converged
run. Stop at the first API failure without rollback; completed changes remain,
including possible partial progress within one RRset. Rerunning the desired
declarations must converge.

Accept `spaceship_dns_api_key` and `spaceship_dns_api_secret`, with fallback to
`SPACESHIP_API_KEY` and `SPACESHIP_API_SECRET` respectively only when the
corresponding variable is unset. Explicit blank credentials fail instead of
falling back. Redact credentials in argument specifications and
credential-bearing tasks, following the Gandi Role's approach.

Add desired values before deleting stale values wherever the provider permits
coexistence. This reduces gaps but can temporarily expose both old and new
values. For mutually exclusive replacements, delete the old value first when
required; a subsequent failure can leave a gap until a successful rerun.

API semantics: [Spaceship API documentation](https://docs.spaceship.dev/).
