# Changelog

## Unreleased

- Provide independently installable Gandi, Vercel, GitHub, and Node.js Collections.
- Manage explicit Gandi LiveDNS RRsets with PAT authentication, validation before
  mutation, check mode, idempotency, and ordered execution that stops on failure.
- Add Vercel Project management and reusable Node.js/GitHub CLI setup.
- Verify live Vercel/GitHub production deployment, historical Deployment reuse,
  and Gandi LiveDNS behaviour, including exact-resource cleanup.
- Provide credential-free contract checks and protected live Molecule scenarios.
- Keep live cleanup manifests outside Molecule ephemeral storage and reset
  lifecycle state between tests.
