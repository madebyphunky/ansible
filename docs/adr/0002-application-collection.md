# Application Collection for cross-provider composition

ADR-0001 keeps provider API logic in independently installable provider
Collections. Application setup still needs a thin composer across GitHub,
Vercel, and Supabase. We package that composer as a small Application
Collection that depends on the provider Collections and owns playbooks/Roles
only for composition and wiring contracts—not provider API implementations—
rather than embedding cross-provider setup inside Vercel or Supabase, or
shipping a loose repo-root playbook outside Collections.
