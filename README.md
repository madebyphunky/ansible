# madebyphunky.infra

Small reusable Ansible Roles that Agents run to maintain project infrastructure.
The repository root is the Collection root. Runtime requirements are Ansible Core
2.18 or later, its supported controller Python, and Collection dependencies.
No additional runtime Python packages are required by the Role.

## Install and discover

```sh
ansible-galaxy collection install git+https://github.com/madebyphunky/ansible.git
```

For a local checkout, use `ansible-galaxy collection install . --force`.
Collection dependencies (including `community.general >= 9.0.0`) are installed by
Galaxy. There is no requirement to publish to Galaxy before using the Collection.

| Role | Purpose |
| --- | --- |
| `madebyphunky.infra.dns_gandi_livedns` | Converge explicitly owned Gandi LiveDNS record sets. |

Each Role's machine-readable interface is its `meta/argument_specs.yml`, with
values in `defaults/main.yml`. See the [Role guide](roles/dns_gandi_livedns/README.md).
The [glossary](GLOSSARY.md) defines the Collection's domain vocabulary.

## Run through a thin playbook

Create a credential-free input file, for example `dns-input.yml`:

```yaml
gandi_livedns_zone: example.com
gandi_livedns_records:
  - name: www
    type: A
    ttl: 300
    values: ["192.0.2.10"]
  - name: old
    type: A
    state: absent
```

Set `GANDI_LIVEDNS_PERSONAL_ACCESS_TOKEN` in your controller environment using your
secret manager or shell, then run the installed Collection playbook:

```sh
ansible-playbook madebyphunky.infra.dns_gandi_livedns -i localhost, -c local -e @dns-input.yml --check
ansible-playbook madebyphunky.infra.dns_gandi_livedns -i localhost, -c local -e @dns-input.yml
```

The playbook defaults to `localhost`, gathers no facts, and only composes the Role.
Override `target_hosts` explicitly if using another inventory host. Prefer local
execution for this API-only Role; the target needs a supported Python and HTTPS
connectivity to Gandi. The environment fallback is always read on the controller.

Alternatively include `madebyphunky.infra.dns_gandi_livedns` in your own playbook.
Use separate invocations for separate zones. Provide the complete desired values
of every present RRset: other tools must not manage values within the same RRset.
Omission leaves records intact; deletion always requires `state: absent`.

Never commit real tokens, secret environment files, vaulted PATs, or examples
containing credentials. Credential-bearing tasks are redacted, including failures.

## Development and verification

Use Python 3.12 for the development tools:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
ansible-galaxy collection install . --force
ansible-lint
black --check tests
pytest -q tests
```

The tests build and install the actual Collection into a temporary directory and
invoke the public Role. An isolated provider double replaces only the external
module, never the Role. These tests do not use Gandi credentials or networking.
They verify validation before mutation, whole-RRset ownership, credential selection
and redaction, convergence, check mode, and stop-on-first-failure semantics.
The PR workflow tests Core 2.18 and 2.19. This is credential-free evidence, not a
substitute for the live acceptance gate.

See [live verification](docs/live-verification.md) for the dedicated-zone Molecule
scenario and protected CI setup. A successful live run is required before calling
the Role ready. Local live acceptance passed on 2026-11-02, including verified cleanup; see the
live verification guide for evidence. Protected CI still needs environment setup.
