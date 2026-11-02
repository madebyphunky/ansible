# Provider-scoped Collections

Provider Roles belong to separate `madebyphunky.vercel`, `madebyphunky.github`,
and `madebyphunky.gandi` Collections, replacing the generic
`madebyphunky.infra` namespace. This gives each provider a clear public Role
family, accepting the additional packaging and dependency management needed
for several Collections in one repository.

The initial public Role names are `madebyphunky.vercel.project`,
`madebyphunky.github.cli`, `madebyphunky.gandi.livedns`, and
`madebyphunky.nodejs.setup`. Node.js setup provides
Node.js, npm, and npx; npx remains an execution mechanism used internally by the
Vercel Role, invoked with `vercel@latest`, rather than a Collection boundary.

The existing Gandi Role migrates from `madebyphunky.infra.dns_gandi_livedns`
to `madebyphunky.gandi.livedns`, including its examples, tests, packaging, and CI
references. This is a clean rename: remove the old invocation without a
compatibility alias, document the replacement, and preserve the existing Gandi
inputs and DNS behaviour.
