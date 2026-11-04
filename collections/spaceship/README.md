# madebyphunky.spaceship

Manage explicitly owned DNS record sets in zones already hosted on Spaceship
with `madebyphunky.spaceship.dns`. Requires Ansible Core 2.18 or 2.19 and
`dnspython >= 2.7` in the Python interpreter executing the module. Galaxy installs
Collections, but does not install Python libraries.

```sh
python -m pip install 'dnspython>=2.7'
ansible-galaxy collection install ./collections/spaceship --force
ansible-playbook madebyphunky.spaceship.dns -i localhost, -c local -e @dns-input.yml --check
ansible-playbook madebyphunky.spaceship.dns -i localhost, -c local -e @dns-input.yml
```

The packaged playbook defaults to localhost, gathers no facts, and accepts an
explicit `target_hosts` override. Prefer local execution for this API-only Role.

Supply `spaceship_dns_zone` and `spaceship_dns_records` in `dns-input.yml`:

```yaml
spaceship_dns_zone: example.com
spaceship_dns_records:
  - name: www
    type: A
    ttl: 300
    values: ['192.0.2.1']
  - name: '@'
    type: MX
    ttl: 300
    values: ['10 mail.example.net.']
  - name: _verification
    type: TXT
    ttl: 300
    values: ['"verification text"']
```

Set `SPACESHIP_API_KEY` and `SPACESHIP_API_SECRET` in the controller environment
through your secret manager. Explicit `spaceship_dns_api_key` and
`spaceship_dns_api_secret` variables override the corresponding environment
values independently. Explicit blank credentials fail. Both DNS read and write
scopes are required. Never commit credentials.

See the [Role guide](roles/dns/README.md) for the complete contract.
