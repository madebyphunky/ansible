# Ansible role library

A public Ansible Collection of small reusable Roles that AI agents run to create and maintain projects.

## Language

**Role**:
A small, single-purpose, reusable Ansible unit with a stable variable interface, written so an agent can compose and run it without reading the whole collection. Playbooks are thin composers; logic lives in Roles.
_Avoid_: module (unless meaning an Ansible module), playbook-as-logic, script

**Collection**:
The installable Ansible namespace that packages Roles for distribution (Galaxy-friendly), e.g. under `madebyphunky`.
_Avoid_: monorepo of loose roles, playbook dump

**Agent**:
An AI coding agent that **runs** Roles via Ansible (`ansible` / `ansible-playbook` or equivalent). It is not a primary documentation reader or a custom tool/MCP consumer of this repo in v1.
_Avoid_: human operator as the primary user, MCP server, docs-only consumer

**LiveDNS**:
Gandi's DNS API surface for managing records on zones already under your control. Domain registration and transfer are out of scope for the first Role.
_Avoid_: Gandi domain API, registrar API

**Managed set**:
The explicitly identified record sets a Role owns, each identified by zone, name, and type and including all values for that combination. Record sets outside the Managed set are never touched.
_Avoid_: full-zone sync, wipe-and-replace, unmanaged delete

**Personal Access Token (PAT)**:
Gandi bearer credential for LiveDNS (`Authorization: Bearer …`). The only auth `dns_gandi_livedns` accepts.
_Avoid_: API key, Apikey
