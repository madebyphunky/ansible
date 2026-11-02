# Changelog

## 0.1.0

- Add the `madebyphunky.infra` Collection and the `dns_gandi_livedns` Role.
- Validate complete explicit RRsets before mutation, with PAT authentication,
  check mode, and ordered execution that stops on failure.
- Add credential-free contract checks and a protected live Molecule scenario.
- Local Gandi acceptance passed on 2026-11-02, including verified cleanup.
