# madebyphunky.nodejs

Reusable Node.js tooling. Invoke `madebyphunky.nodejs.setup` to ensure Node.js,
npm, and npx are available. The Role inspects local version commands without
resolving or downloading npm packages, and reuses a compatible installation.

## Inputs and results

| Variable | Default | Purpose |
| --- | --- | --- |
| `nodejs_node_executable` | `node` | Existing Node.js executable name or absolute path. |
| `nodejs_npm_executable` | `npm` | Existing npm executable name or absolute path. |
| `nodejs_npx_executable` | `npx` | Existing npx executable name or absolute path. |
| `nodejs_install` | `true` | Permit setup when an existing runtime is unavailable/incompatible. |
| `nodejs_lts_major` | `26` | LTS major installed when setup is required. |
| `nodejs_compatible_majors` | `[22, 24, 26]` | Existing supported LTS majors accepted for reuse. |

Node.js 26 is the current Active LTS as verified on 2026-11-02; update the LTS
policy as the upstream schedule changes. Existing supported Maintenance LTS
runtimes are also accepted. A full runtime requires working `node`, `npm`, and
`npx` version commands, not just a Node.js executable.

The public `nodejs_runtime` fact includes `node_path`, `npm_path`, `npx_path`,
`node_major`, `available`, and `planned`. Prepend the directory containing
`node_path` to subprocess PATH when using npm/npx, so their Node.js shebang uses
the selected runtime. This Role does not rewrite login-shell configuration.

## Supported installation

- macOS requires Homebrew already available. Install the selected `node@26`
  formula (Homebrew currently aliases it to `node`) without sudo; use its formula
  prefix directly, so keg-only installations remain usable.
- Ubuntu/Debian use the signed NodeSource repository for the requested LTS major,
  then install its `nodejs` package, which includes npm and npx. Package/repository
  tasks use privilege escalation; configure Ansible become credentials as needed.
  No remote setup script is piped into a shell.
- Other operating systems/distributions fail clearly, including when tools exist.

Check mode only inspects tools and platform facts. Missing tools yield
`available: false`, `planned: true`, and a predicted change, without downloading
packages or changing repositories. Normal mode with installation disabled fails
if the complete compatible runtime is unavailable.

Use the bundled thin `setup` playbook with localhost as its safe default, or
include the Role in a composing playbook. The Collection requires Ansible Core
2.18+ and declares its Homebrew module dependency on community.general.

Sources: [Node.js release policy](https://nodejs.org/en/about/previous-releases),
[NodeSource package instructions](https://github.com/nodesource/distributions/blob/master/DEV_README.md),
[Homebrew Node formula](https://formulae.brew.sh/formula/node).
