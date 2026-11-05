# madebyphunky.dokku

Create or reuse one explicitly named Dokku App with the reusable
`madebyphunky.dokku.app` Role. The Role runs on the Ansible controller and sends
native Dokku commands over SSH as the `dokku` user. CI owns every release,
including the first. Dokku and Kamal are never used together. See
[ADR-0005](../../docs/adr/0005-dokku-app-configuration-boundary.md).

## Prerequisites

Run on the controller (`hosts: localhost`, `connection: local`) with Ansible
Core 2.18 or 2.19 and OpenSSH. The Dokku host must already exist and already
have Dokku installed. Supply SSH configuration, credentials, and host
verification yourself. This Role does not register keys, provision CI
credentials, install Dokku, or provision a VPS.

The `version`, `apps:exists`, and `apps:create` command contract was read from
Dokku 0.34.0 and tested release 0.38.34. `dokku version` must print
`dokku version X.Y.Z`. A missing App makes `apps:exists` exit 20. Versions
outside 0.34.0 through 0.38.34, and unrecognized version output, fail before
any mutation. The Role never upgrades the host. Live SSH acceptance passed against official
Dokku containers for both endpoints on 2026-11-05; see
[verification evidence](../../docs/dokku-verification.md).

Install from this repository with `python scripts/collection_tools.py install`.
The Collection has no dependency on another Collection.

## Use

Staging and production are separate Dokku App names. Pass those names
explicitly. The Role has no environment input and does not invent one.

```yaml
- name: Create or reuse one Dokku App
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - role: madebyphunky.dokku.app
      dokku_host: 203.0.113.10
      dokku_app: billing
```

A staging App is another call, for example `dokku_app: billing-staging` on the
host where that App should live. The thin example playbook is
`playbooks/app.yml`; pass the same variables with `-e`:

```sh
ansible-playbook madebyphunky.dokku.app -e dokku_host=203.0.113.10 -e dokku_app=billing
```

`ansible-playbook madebyphunky.dokku.app` resolves the installed example. From a
checkout, run `collections/dokku/playbooks/app.yml` the same way.

| Input | Contract |
| --- | --- |
| `dokku_host` | Required hostname or IPv4 address of an existing Dokku host. |
| `dokku_app` | Required explicit Dokku App name. Lowercase alphanumeric first character; then lowercase alphanumerics, dots, and hyphens. |
| `dokku_ssh_port` | Optional SSH port override; otherwise use SSH configuration (OpenSSH defaults to `22`). |
| `dokku_ssh_private_key` | Optional absolute path to an existing private key. Not created or registered. |
| `dokku_ssh_known_hosts` | Optional absolute path. When set, it is the only known-hosts file. |
| `dokku_ssh_config` | Optional absolute path, passed as `ssh -F`. Replaces the default SSH config. |
| `dokku_ssh_executable` | Existing executable or wrapper, default `ssh`. Not a shell command string. |

Commands always run as `dokku@dokku_host`. `BatchMode=yes` is set on the
command line, so it takes precedence over `dokku_ssh_config` and a missing host
key fails instead of prompting or recording a new key. The Role does not set a
connect timeout, `StrictHostKeyChecking=no`, or `accept-new`. When
`dokku_ssh_private_key` is set, `IdentitiesOnly=yes` offers only that key.
When `dokku_ssh_known_hosts` is set, `GlobalKnownHostsFile=/dev/null` makes
that file the only host-key source. Remaining SSH settings come from
`dokku_ssh_config` or, when that input is omitted, from OpenSSH defaults.

## State and limitations

The Role reads `version`, then `apps:exists`. A missing App is created with
`apps:create` unless check mode is on. An existing App is reused. Nothing else
is changed: no source is deployed, and no other App or host setting is edited.
A second identical run reports no change.

Check mode still inspects the live host and reports `actions: ["create"]` with
`planned: true` when the App is absent. It does not create the App.

`dokku_app_result` returns the sanitized host, Dokku App name, reported
version, and `actions`. `actions` is `["create"]` only when the App was
created or check mode would create it. Reuse returns `[]`. Results omit SSH
output, key material, and credentials.

If `apps:create` fails, the Role inspects the App again and does not delete it.
A present App is kept for a rerun, which reuses it. An absent App is reported
as absent. There is no automatic rollback.

Storage, backing services, plugins, scaling, scheduled tasks, and host-wide
configuration are outside v1. So are certificates, DNS, and global Dokku
settings. App-scoped environment values and domains are separate later work
and stay limited to the one named Dokku App.

## CI handoff

Keep release workflows in the consuming Application. CI performs the first
release and every later one. Creating the Dokku App does not publish a release
and does not mean the App is running or publicly reachable.

## Verification

Credential-free contracts build and install the Collection and run the public
Role through an SSH/Dokku double. They cover validation before any connection,
creation, reuse, unsupported versions, SSH failure, and check mode. Live SSH acceptance additionally exercised the installed Role against real
Dokku 0.38.34 and 0.34.0 containers: missing-App check mode, creation, unchanged
reuse, and existing-App check mode. This verifies the App command contract,
not source deployment, plugins, or a production host configuration. See the
[recorded results and rerun procedure](../../docs/dokku-verification.md).

References: [application management](https://dokku.com/docs/deployment/application-management/),
[remote commands](https://dokku.com/docs/deployment/remote-commands/).
