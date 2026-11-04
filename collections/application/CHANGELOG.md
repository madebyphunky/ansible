# Changelog

## 0.2.0

- Add optional DNS composition and Kamal server preparation playbook; CI owns deployments.

## 0.1.0

- Initial Application Collection with local `.env.local` writing Role.
- Add phased `playbooks/setup.yml` composer for GitHub, Vercel, and Supabase.
- Gate Deployment on `vercel_git_sha` and Auth on `application_auth_config` so
  stage-local Role inputs are not overridden by play-level extra-vars.
- Document Application live verification expectations (pending until recorded).
- Reject false/empty stage-input overrides before provider changes.
- Add a validated Supabase environment name map and keep retrieved values
  consistent across production and local wiring.
