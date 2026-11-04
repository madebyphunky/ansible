# dns

`madebyphunky.spaceship.dns` manages complete explicitly declared record sets in
one existing Spaceship DNS zone. Registration, domain transfer, and changing the
zone's authoritative nameservers are outside scope. NS records for delegating
child zones are supported.

| Input | Meaning |
| --- | --- |
| `spaceship_dns_zone` | Required zone without a trailing dot. |
| `spaceship_dns_records` | Required nonempty list of explicit RRsets. |
| `spaceship_dns_api_key` | API key, otherwise controller `SPACESHIP_API_KEY`. |
| `spaceship_dns_api_secret` | Secret, otherwise controller `SPACESHIP_API_SECRET`. |

The executing Python interpreter needs `dnspython >= 2.7`. Credentials need
`dnsrecords:read` and `dnsrecords:write`. Unset credentials fall back independently;
explicit blank values fail. Argument specifications and API tasks redact secrets.

Each entry has `name`, uppercase `type`, optional `state` (`present` by default,
or `absent`), `ttl`, and `values`. Names are relative, or `@` for apex. Absolute
names and names containing the zone suffix are rejected. Duplicate identities,
including case aliases, and unknown fields fail. For `present`, TTL must be an
explicit integer between 60 and 3600 seconds (Spaceship's range), and values a
nonempty list of DNS presentation strings. Duplicate values fail. For `absent`,
TTL and values are ignored; prefer just name, type and state.

Supported API types and value examples:

| Type | Example value |
| --- | --- |
| A | `192.0.2.1` |
| AAAA | `2001:db8::1` |
| ALIAS, CNAME, NS, PTR | `target.example.net.` |
| MX | `10 mail.example.net.` |
| TXT | `"hello world"` |
| CAA | `0 issue "letsencrypt.org"` |
| SRV | `10 20 5060 sip.example.net.` |
| TLSA | `3 1 1` followed by a hexadecimal certificate association |
| HTTPS, SVCB | `1 . alpn="h2,h3"` |

Use complete target domain names; a final dot is optional and removed for the
provider. Relative targets are not expanded against the zone. TXT quoting and
escapes use DNS presentation syntax; adjacent quoted chunks are concatenated
into Spaceship's single text value. TXT content comparisons are case-sensitive;
other content follows the provider's case-insensitive matching. DNS address and
service-parameter representations are normalized for comparison.

Supply the full relative owner for service records: `_sip._tcp` for SRV,
`_443._tcp.www` for TLSA, and optionally `_8443._https.www` for HTTPS or
`_8443._tcp.www` for SVCB. The module translates service/port labels into the
provider's separate fields. CNAME and ALIAS accept one value only.

The complete batch is validated before any provider call. Provider-specific
restrictions can still fail at execution. Each entry owns all values for its
zone/name/type; present replaces complete content and TTL, absent removes the
complete RRset, and omission leaves other sets untouched. Product and personal
nameserver records are protected. Conflicting records of other types are never
pruned to make room for a CNAME. No force option is exposed.

The module reads every page before changes, then applies declarations in order.
It adds desired values before deleting stale ones where possible. CNAME and
ALIAS replacements delete stale values first. Changes can temporarily expose
both old and new values, or leave a gap for exclusive replacements. Requests
are limited to 500 records. The first failure stops the run without rollback or
automatic retry; successful changes remain, possibly within one RRset. Rerun to
converge. Callers must ensure a single writer per RRset.

Check mode reads current provider state and predicts changes without mutations.
A second identical run after convergence reports no changes. Credential-bearing
tasks are redacted, including their provider error details.

Credential-free tests cover translation, reconciliation and the installed Role
through a local API double. Live Spaceship acceptance has not been performed.
API reference: https://docs.spaceship.dev/.
