# Kamal deployment handoff to CI

Ansible prepares an existing VPS for Kamal; the consuming Application's CI owns
all Application deployments, including the first. Application and environment
isolation belong to Kamal configuration and CI rather than this Role. The
Collection documents the handoff; CI workflow creation and credential provisioning
belong to the consuming Application. This keeps release orchestration out of
infrastructure configuration and keeps the reusable Role independent of a CI
provider.

Optional DNS automation is composed through a thin Application playbook using the
existing DNS Roles, preserving ADR-0002's cross-provider boundary.

Server preparation ensures Docker is installed and its daemon is accessible,
using Kamal's native `server bootstrap` only when Docker is absent. Existing
Docker with an inaccessible daemon produces a diagnostic failure rather than
introducing a separate repair mechanism. Proxy startup, routing, HTTPS,
accessories, and registry login remain with CI's Kamal deployment.

The Role runs on the Ansible controller with an existing Kamal executable and
SSH access. It accepts either a path to native Kamal configuration or Role
variables containing the same native configuration values; it does not introduce
a parallel schema for Kamal options.

Project hooks are disabled during Role operations to preserve this boundary.
Native Kamal inspection writes audit entries even on no-op and check-mode runs;
check mode predicts installation without changing Docker or DNS.
