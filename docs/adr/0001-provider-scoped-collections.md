# Provider-scoped Collections

Provider Roles belong to independently installable `madebyphunky.vercel`,
`madebyphunky.github`, `madebyphunky.gandi`, and `madebyphunky.nodejs` Collections.
Each provider has a clear public Role family, with shared tooling handling
packaging and dependencies across the repository.

The public Roles are `madebyphunky.vercel.project`, `madebyphunky.github.cli`,
`madebyphunky.gandi.livedns`, and `madebyphunky.nodejs.setup`. Node.js setup
provides Node.js, npm, and npx; npx is an execution mechanism used internally by
the Vercel Role with `vercel@latest`, rather than a Collection boundary.
