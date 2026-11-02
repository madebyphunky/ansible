# madebyphunky.github

`madebyphunky.github.cli` ensures the GitHub CLI is available for composing Roles.
It inspects `gh --version`, reuses a working installation, and does not authenticate
or read the user's saved login. Provider Roles supply their own explicit identity
and shared `GH_TOKEN` credential when making API calls.

## Inputs and results

| Variable | Default | Purpose |
| --- | --- | --- |
| `github_cli_executable` | `gh` | Existing executable name or absolute path. |
| `github_cli_install` | `true` | Permit installation when the CLI is unavailable. |

The public `github_cli_result` fact includes `path`, `available`, and `planned`.
Normal mode fails clearly if installation is disabled and no usable executable
exists. Check mode returns a predicted change and `available: false, planned:
true` for missing tools without installing packages or downloading artifacts.

## Supported installation

macOS requires Homebrew already on PATH and installs `gh` without sudo. Ubuntu
and Debian use the official signed GitHub CLI APT repository and package, with
Ansible become privileges for package/repository setup. Other platforms fail
clearly. Existing installations are reused rather than upgraded implicitly.

The Collection requires Ansible Core 2.18+ and community.general for Homebrew.
Use the bundled thin `cli` playbook, defaulting safely to localhost, or include
`madebyphunky.github.cli` in another playbook.

Source: [official GitHub CLI Linux installation instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md).
