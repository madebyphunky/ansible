# madebyphunky.hetzner

`madebyphunky.hetzner.server` creates one new Hetzner Cloud server per invocation
on the controller. Install this Collection with Galaxy (or the repository installer);
its pinned official `hetzner.hcloud ==6.12.0` dependency supports Ansible Core
2.18 and 2.19 (`requires_ansible >=2.18`). Provider API logic stays in that official
Collection. No external Python SDK is required by this provider version.

```yaml
- hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - role: madebyphunky.hetzner.server
      hetzner_server_name: example-web-01
      hetzner_server_image: ubuntu-24.04
      hetzner_server_type: cx23
      hetzner_server_location: nbg1
      hetzner_server_ssh_keys: [existing-operator-key]
      # hetzner_server_firewall: existing-web-firewall
  tasks:
    - ansible.builtin.debug:
        var: hetzner_server_result
```

Set controller environment `HCLOUD_TOKEN`, or pass the redacted
`hetzner_server_api_token` Ansible variable (explicit values take precedence,
including an explicitly empty value which fails validation). Never commit tokens.
Name, image, type, location and a nonempty list of existing SSH key names/IDs are
required. An optional firewall must already exist. Invalid provider references
are resolved by the official module before creation. No SSH keys, firewalls,
private networks or volumes are created.

Public IPv4 and IPv6 default to enabled. **Public IPv4 incurs a separate Hetzner
charge**; consult current Hetzner pricing. Set `hetzner_server_enable_ipv4: false`
or `hetzner_server_enable_ipv6: false` explicitly to disable either address family.

On success, `hetzner_server_result` contains `id`, `ipv4`, `ipv6` (the provider's
IPv6 network/CIDR), and `status: running`. Disabled address families return null.
This means provider running status only, not SSH readiness. Check mode performs
read-only provider validation and predicts creation with a changed result; no ID
or addresses are invented (`hetzner_server_result` is empty).

An existing name is rejected without adoption. `hetzner_server_id` is explicitly
unsupported, even when empty. This is a creation-only Role; repeat runs fail on
the existing name. Serialize operations for a given project/name: the official
module's lookup/create sequence does not provide an atomic create-only guard
against concurrent external creators.

On any failure, resources remain in place. The Role attempts a read-only exact-name
lookup and exposes the recovered ID in `hetzner_server_result` and the failure
message. If that lookup also fails, find the server by exact name in the Hetzner
Cloud console/API and preserve its stable ID before recovery. A recovered ID may
belong to a pre-existing name collision; it does not prove this invocation created
it. Do not blindly retry, rename, or delete after an uncertain outcome. Explicit-ID
adoption and repeat-run verification are deferred to a later slice.

No cloud-init customization, host configuration, Kamal preparation, deployments,
rebuilding, resizing, deletion, fleet orchestration or provider-neutral abstraction
is included. Automated verification uses isolated official-module doubles; it
never creates billable resources.
