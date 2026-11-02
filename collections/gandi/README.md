# madebyphunky.gandi

Manage explicitly owned Gandi LiveDNS record sets through the reusable
`madebyphunky.gandi.livedns` Role. Requires Ansible Core 2.18 or later and
`community.general >= 9.0.0`; Galaxy installs Collection dependencies.

## Install

From the repository checkout:

```sh
ansible-galaxy collection install ./collections/gandi --force
```

Alternatively build this Collection and install its archive. The repository hosts
several independent Collections; the repository root is not a Collection.

## Run

Supply `gandi_livedns_zone` and a nonempty `gandi_livedns_records` list through
an input file. Set the controller environment variable
`GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN` through your secret manager, or explicitly
supply `gandi_livedns_personal_access_token` (which takes precedence).

```sh
ansible-playbook madebyphunky.gandi.livedns -i localhost, -c local -e @dns-input.yml --check
ansible-playbook madebyphunky.gandi.livedns -i localhost, -c local -e @dns-input.yml
```

The thin example playbook defaults to localhost, gathers no facts, and accepts an
explicit `target_hosts` override. Prefer local execution for this API-only Role.

Each declaration names a relative `name` (or `@` for apex) and uppercase `type`.
Present entries require an explicit integer `ttl` and a complete nonempty string
`values` list. `state` defaults to `present`; `state: absent` explicitly deletes
the complete RRset. Omission leaves existing records untouched.

See the [Role guide](roles/livedns/README.md), its machine-readable argument
specification and defaults for the complete interface. See repository
[live verification](https://github.com/madebyphunky/ansible/blob/main/docs/live-verification.md)
for protected acceptance requirements and exact-identity cleanup.

## Migration

Replace `madebyphunky.infra.dns_gandi_livedns` with
`madebyphunky.gandi.livedns` and install this Collection. There is no compatibility
alias. Variables, PAT fallback, validation, idempotency, and DNS behaviour remain
unchanged. Never commit real credentials, secret environment files, or vaulted PATs.
