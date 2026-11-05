# Dokku App configuration stays on the host; CI owns releases

A Dokku App is an explicitly named app on an existing Dokku host. This
Collection creates and inspects that App through native commands over SSH as
the `dokku` user, and later slices may converge only that App's environment
values and domains. It does not install Dokku, provision the host, register SSH
keys, provision CI credentials, or deploy source. The consuming Application's
CI owns every release, including the first. Staging and production are separate
Dokku App names supplied by the caller.

Dokku and Kamal are never used together. Storage, backing services, plugins,
scaling, scheduled tasks, certificates, DNS, and host-wide configuration are
outside v1. Failures keep completed changes so a rerun can inspect them; there
is no automatic rollback. This extends ADR-0001's provider-scoped Collections
and ADR-0004's CI handoff to a separate tool that does not compose with Kamal.
