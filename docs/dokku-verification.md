# Dokku App verification

Live SSH acceptance passed on 2026-11-05 against official Dokku 0.38.34 and
0.34.0 containers, using the built/installed `madebyphunky.dokku.app` Role
from commit `8725720ace69b04c6b7513933b960cc8ca1140d8`. The controller used
Ansible Core 2.19 and Python 3.12 on macOS with Docker Desktop Engine 29.8.2.

[Sanitized results and immutable image digests](dokku-live-evidence.json)
record the public result fields from each run. Both releases passed:

| Phase | changed | exists | planned | actions |
| --- | --- | --- | --- | --- |
| Missing App, check mode | true | false | true | create |
| Create App | true | true | false | create |
| Reuse App | false | true | false | none |
| Existing App, check mode | false | true | false | none |

After each phase, direct `dokku apps:exists acceptance-29` inside the container
independently confirmed the observed state: exit 20 after prediction, exit 0
thereafter. No Release was published. Both temporary containers and their
anonymous data volumes were removed after verification.

## Rerun

Use a disposable host, not an existing production App. For container setup use
[Dokku's versioned Docker installation instructions](https://github.com/dokku/dokku/blob/v0.38.34/docs/getting-started/install/docker.md).
The acceptance fixture published only SSH on a random loopback port, used an
anonymous `/mnt/dokku` volume and the local Docker socket, and generated a
temporary Ed25519 client key. The fixture registered its public key through
`docker exec -i CONTAINER dokku ssh-keys:add acceptance`; the Role itself
never registers keys. Wait for a successful SSH `version` command before testing.

Build and install the Collection into an isolated directory. Run its installed
`playbooks/app.yml` against each version with these explicit variables:

```yaml
dokku_host: live-dokku
dokku_app: acceptance-29
dokku_ssh_config: /absolute/path/to/config
dokku_ssh_private_key: /absolute/path/to/temporary-key
dokku_ssh_known_hosts: /absolute/path/to/known_hosts
```

The SSH config maps `live-dokku` to `127.0.0.1`, sets the published port, and
sets `StrictHostKeyChecking yes`. Obtain the host's public key directly from
the owned container, and write `[127.0.0.1]:PORT KEYTYPE PUBLICKEY` to the
known-hosts file. No verification bypass or trust-on-first-use is necessary.
Omit `dokku_ssh_port` to exercise the caller's SSH-configured port.

Run check mode, ordinary mode twice, then check mode again. Register and inspect
`dokku_app_result` and compare against the table above. Confirm the actual App
state independently after each run. Remove only the disposable containers and
their volumes; retain sanitized output and image digests for future evidence.

## Scope

0.38.34 is the tested reference release; 0.34.0 is the tested lower bound.
Intermediate versions in the advertised inclusive range are not individually
tested. This exercise verifies real SSH and native App command behavior in the
official images. It does not validate production host configuration, source
deployment, storage, backing services, plugins, scaling, or scheduled tasks.
Credential-free contracts cover rejected versions, input validation, SSH
failures, and partial-creation recovery separately.
