# madebyphunky.kamal

Prepare existing VPS hosts for Kamal with the reusable
`madebyphunky.kamal.setup` Role. CI runs all Application deployments, including
the first. The Role uses native `kamal server bootstrap` to install missing Docker;
it does not provision a VPS, install Kamal, or deploy an Application.

## Prerequisites

Run on the Ansible controller (`hosts: localhost`, `connection: local`) with
Ansible Core 2.18 or 2.19, controller Python with PyYAML (provided by Ansible), an
existing Kamal 2.12 executable, a checkout directory, valid native Kamal
configuration, and working SSH access. This implementation targets Kamal 2.12's
raw server-exec output; other versions have not been verified. A wrapper executable
may invoke a project's bundled Kamal. Registry configuration can be required by
Kamal's config validation even though bootstrap does not log into a registry.

Install from this repository with `python scripts/collection_tools.py install`.
The Collection has no dependency on a Docker or DNS Collection.

## Use

```yaml
- name: Prepare a VPS for later CI deployment
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - role: madebyphunky.kamal.setup
      kamal_workdir: /path/to/application
      kamal_config_file: config/deploy.yml
```

Alternatively, omit `kamal_config_file` and provide the native values as a mapping:

```yaml
kamal_workdir: /path/to/application
kamal_config:
  service: example
  image: example/app
  servers:
    web:
      - 192.0.2.10
  registry:
    server: registry.example.com
    username: example
    password:
      - KAMAL_REGISTRY_PASSWORD
```

Kamal validates these values; the Role does not mirror its configuration schema.
Do not include secret literals in checked-in vars. Pass required process values
through `kamal_environment`, Ansible Vault, or the controller environment, using
Kamal's native secret references. Configuration and environment module inputs are
redacted, and CLI output is withheld on failure because it can contain secrets.
Kamal config files and ERB must be trusted inputs.

| Input | Contract |
| --- | --- |
| `kamal_workdir` | Required existing controller directory; process working directory. |
| `kamal_config_file` | Native config path, relative to workdir or absolute. |
| `kamal_config` | Native configuration mapping; mutually exclusive with config file. Exactly one input is required. |
| `kamal_executable` | Existing executable or wrapper, default `kamal`; not a shell command string. |
| `kamal_destination` | Optional native destination selector; no environment orchestration. |
| `kamal_environment` | Redacted environment overrides, default `{}`. |

Mapping input is written to a private temporary YAML file and removed on success
or failure. This also happens in check mode so Kamal can validate and inspect.
It is not persisted for CI. Relative project assets resolve from `kamal_workdir`;
if you need destination overlay files adjacent to a base config, use file input.
Caller-owned files are never rewritten.

## State and limitations

The Role inspects all hosts selected by native Kamal configuration. It verifies
Docker client and daemon access, bootstraps when at least one host lacks Docker,
and verifies again. Already usable hosts produce no Ansible change. Missing
Docker installation requires privileges and tooling supported by Kamal's installer.
Existing but unusable Docker, SSH errors, invalid config, unexpected output, and
failed post-install verification fail; no separate repair mechanism is provided.
A mixed fleet with an inaccessible daemon fails before bootstrap.

All operations use `--skip-hooks`, including bootstrap, so project hooks cannot
expand this Role into release orchestration. Native `server exec` appends remote
Kamal audit entries, including on no-op and check-mode runs. Check mode predicts
Docker installation without invoking bootstrap; it does not change Docker or DNS.
No local marker stands in for live inspection.

`kamal_setup_result` exposes `changed`, `ready`, and `planned`. In check mode,
missing Docker returns `ready: false`, `planned: true`. A failed bootstrap may
leave a partial Docker installation; fix the reported prerequisite and rerun.

## DNS and CI handoff

The optional `madebyphunky.application.kamal_setup` playbook composes existing
DNS Roles and this Role. See the Application Collection README. Direct use of
this Role requires no DNS inputs. DNS ownership remains explicit record sets.

Keep durable Kamal config in the Application repository for CI. CI owns Kamal's
first deployment (typically `kamal setup`), registry login, proxy startup, routing,
HTTPS, accessories, and later releases. Multiple apps and staging/production use
native Kamal identities/configuration/destinations; the Role adds no model for
those. Existing releases are untouched by bootstrap. Shared proxy changes belong
to that deployment workflow.

## Verification

Credential-free contracts build/install the actual Collection and run the public
Role through a CLI double. Live VPS acceptance is **pending**. Before claiming live
compatibility, use an explicitly authorized disposable VPS: inspect check mode,
bootstrap missing Docker, verify daemon access, rerun with zero Ansible changes,
and confirm no Application/proxy was deployed. Test both config forms, a broken
SSH/daemon case, and optional DNS with an explicitly owned disposable record set;
clean up those exact resources. No live server has been provisioned by this change.

References: [server commands](https://kamal-deploy.org/docs/commands/server/),
[configuration](https://kamal-deploy.org/docs/configuration/overview/),
[installation](https://kamal-deploy.org/docs/installation/).
