# Ansible role library

A public Ansible Collection of small reusable Roles that AI agents run to create and maintain projects.

## Language

**Role**:
A small, single-purpose, reusable Ansible unit with a stable variable interface, written so an agent can compose and run it without reading the whole collection. Playbooks are thin composers; logic lives in Roles.
_Avoid_: module (unless meaning an Ansible module), playbook-as-logic, script

**Collection**:
An independently installable Ansible namespace that packages Roles for distribution, such as `madebyphunky.vercel`.
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

**Spaceship DNS**:
Spaceship's DNS service for records in zones already hosted there. Domain registration, transfer, and nameserver changes are outside this Role's scope.
_Avoid_: LiveDNS (Gandi-specific), domain migration, registrar management

**Personal Access Token (PAT)**:
Gandi bearer credential for LiveDNS (`Authorization: Bearer …`). The only auth the Gandi LiveDNS Role accepts.
_Avoid_: API key, Apikey

**Application**:
The product being built, independent of its source host, hosting providers, or deployment tooling.
_Avoid_: project (when referring to the whole product rather than a provider Project)

**Infrastructure setup**:
Creating or linking the GitHub repository, Vercel Project, and Supabase Project for an Application. It can complete before application source exists.
_Avoid_: project creation, Deployment, scaffolding

**Vercel Project**:
An application container within an explicitly selected Vercel account or team. It can exist without a Deployment or application source.
_Avoid_: Deployment (when referring to the Project itself)

**Deployment**:
A published version of an application's source within a Vercel Project, associated with a deployment URL. A production Deployment is the version published for production use.
_Avoid_: Project (when referring to a published version)

**Supabase Project**:
A hosted Supabase environment containing a Postgres database and associated backend services within a Supabase organization.
_Avoid_: self-hosted stack, local development stack, database (when referring to the whole Project)

**Supabase Organization**:
The hosted Supabase account boundary containing Supabase Projects.
_Avoid_: Project, team (when referring to the Supabase ownership boundary)

**Project reference**:
Supabase's stable identifier for a hosted Supabase Project, distinct from its display name.
_Avoid_: project name (when selecting an exact existing Supabase Project)
