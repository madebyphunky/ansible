# Kamal server setup

## Scope

Add an independently installable `madebyphunky.kamal` Collection following the
repository's packaging, argument specification, documentation, and contract-test
conventions. Its small reusable setup Role prepares existing VPS hosts for Kamal.
The consuming Application's CI owns every Application deployment, including the
first. See [ADR-0004](../adr/0004-kamal-deployment-handoff.md).

## Configuration and execution

Run Kamal on the Ansible controller using an existing executable and existing SSH
access. Accept either a native Kamal configuration file path or Role variables
containing native Kamal configuration values. Reject conflicting inputs. Preserve
Kamal's configuration keys rather than maintain a duplicate option schema.

For variable input, serialize configuration to a temporary YAML file and remove
it afterward, including on failure. Read caller-owned configuration files without
modification. CI owns its durable configuration, workflows, and credentials;
document the handoff rather than generate CI workflows.

Application and environment isolation remain in Kamal configuration and CI.
Multi-application and staging/production configuration introduce no independent
orchestration model in this Collection.

## Server state

Inspect actual remote Docker state rather than rely on local completion markers.
Use native `kamal server bootstrap` only when Docker is absent. Verify daemon
accessibility afterward. An existing installation with an inaccessible daemon
fails with a useful diagnostic; Docker repair is outside this Role's scope.
Inspection errors must not be interpreted as missing Docker.

Do not invoke `kamal setup`, which includes deployment. Proxy startup, routing,
HTTPS, accessories, registry login, and all Application deployments remain with
CI's Kamal operations. Rerunning server setup must leave existing releases alone
and report no change when Docker is already usable.

## Optional DNS

A thin playbook in `madebyphunky.application` optionally composes existing DNS
Roles with the Kamal setup Role, preserving ADR-0002. Reuse the DNS Roles' explicit
record-set ownership and credential contracts. DNS is not required to run server
bootstrap; it is preparation for the later CI deployment.

## Check mode and verification

Check mode inspects server state and predicts bootstrap without installing Docker
or mutating DNS. Connection and configuration errors fail rather than report a
planned change. Existing DNS Roles provide DNS change prediction. Native
`server exec` writes remote Kamal audit entries even during inspection. All Role
operations disable project hooks to preserve the server-preparation boundary.

Credential-free contracts build/install the Collection and exercise its public
Role with isolated command/provider doubles. Cover both configuration inputs,
input conflicts, temporary-file cleanup, usable-Docker no-op, absent-Docker
bootstrap and verification, inaccessible-daemon failures, inspection failures,
check-mode behavior, and optional DNS composition. Run the repository's required
checks. Live VPS acceptance remains separately gated and must be reported as
performed or pending; doubles do not establish live compatibility.

## Native references

- [Kamal server commands](https://kamal-deploy.org/docs/commands/server/)
- [Kamal setup includes deployment](https://kamal-deploy.org/docs/commands/setup/)
- [Native configuration](https://kamal-deploy.org/docs/configuration/overview/)
- [Kamal installation prerequisites](https://kamal-deploy.org/docs/installation/)
