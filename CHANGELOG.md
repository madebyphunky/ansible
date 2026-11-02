# Changelog

## Unreleased

- Split provider Roles into independently installable gandi, vercel, github, and
  nodejs Collections; the repository root is no longer a Collection.
- Rename the Gandi Role to `madebyphunky.gandi.livedns` without an alias; inputs
  and DNS behaviour are unchanged.
- Add Vercel Project management and reusable Node.js/GitHub CLI setup.
- Verify live Vercel/GitHub production deployment, historical reuse, and cleanup,
  plus live acceptance of the renamed Gandi Role.
- Keep live cleanup manifests outside Molecule ephemeral storage and reset
  lifecycle state between tests.

## 0.1.0

- Add the `madebyphunky.infra` Collection and the `dns_gandi_livedns` Role.
- Validate complete explicit RRsets before mutation, with PAT authentication,
  check mode, and ordered execution that stops on failure.
- Add credential-free contract checks and a protected live Molecule scenario.
- Local Gandi acceptance passed on 2026-11-02, including verified cleanup.
