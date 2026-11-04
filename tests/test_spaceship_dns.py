"""Spaceship translation, ownership, and installed Role contracts."""

import copy
import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from runner import changed, invoke

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "spaceship_dns", ROOT / "collections/spaceship/plugins/module_utils/dns_records.py"
)
dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dns)


def entry(**kwargs):
    return dict(name="www", type="A", ttl=300, values=["192.0.2.1"]) | kwargs


def existing(**kwargs):
    return (
        dict(
            type="A", name="www", ttl=300, address="192.0.2.2", group={"type": "custom"}
        )
        | kwargs
    )


class Provider:
    def __init__(self, records=(), fail=None):
        self.records = copy.deepcopy(list(records))
        self.calls = []
        self.fail = fail

    def request(self, method, query, body):
        self.calls.append((method, query, body))
        if method == self.fail:
            raise ValueError("simulated provider failure")
        if method == "GET":
            skip = int(query.split("skip=")[1])
            return {
                "items": self.records[skip : skip + 500],
                "total": len(self.records),
            }
        if method == "PUT":
            assert body["force"] is False
            for item in body["items"]:
                key = dns.content_key(item)
                self.records = [r for r in self.records if dns.content_key(r) != key]
                self.records.append(dict(item, group={"type": "custom"}))
        else:
            keys = {dns.content_key(item) for item in body}
            self.records = [r for r in self.records if dns.content_key(r) not in keys]


@pytest.mark.parametrize(
    "kind,name,value,field,expected",
    [
        ("A", "www", "192.0.2.1", "address", "192.0.2.1"),
        ("AAAA", "www", "2001:db8::1", "address", "2001:db8::1"),
        ("ALIAS", "@", "example.net.", "aliasName", "example.net"),
        ("CNAME", "www", "example.net.", "cname", "example.net"),
        ("MX", "@", "10 mail.example.net.", "preference", 10),
        ("NS", "child", "ns.example.net.", "nameserver", "ns.example.net"),
        ("PTR", "1", "host.example.net.", "pointer", "host.example.net"),
        ("TXT", "@", '"hello " "world"', "value", "hello world"),
        ("CAA", "@", '0 issue "letsencrypt.org"', "tag", "issue"),
        ("SRV", "_sip._tcp", "10 20 5060 sip.example.net.", "port", 5060),
        ("TLSA", "_443._tcp.www", "3 1 1 " + "ab" * 32, "matching", 1),
        ("HTTPS", "www", '1 . alpn="h2,h3"', "svcPriority", 1),
        ("SVCB", "_8443._tcp.www", "1 svc.example.net. port=8443", "svcPriority", 1),
    ],
)
def test_supported_translation(kind, name, value, field, expected):
    record = dns.translate(name, kind, 300, value)
    assert record[field] == expected
    assert dns.owner(record) == name
    assert dns.content_key(record)


@pytest.mark.parametrize(
    "declarations",
    [
        [],
        [entry(ttl="300")],
        [entry(ttl=True)],
        [entry(ttl=59)],
        [entry(values=[1])],
        [entry(values=[])],
        [entry(values=["bad-ip"])],
        [entry(type="BOGUS")],
        [entry(name="www.example.com")],
        [entry(name="www.")],
        [entry(typo=True)],
        [entry(state="unknown")],
        [entry(), entry(name="WWW")],
        [entry(values=["192.0.2.1", "192.0.2.1"])],
        [entry(), entry(type="SRV", values=["10 20 5060 sip.example.net."])],
    ],
)
def test_invalid_batch(declarations):
    with pytest.raises(Exception):
        dns.validate("example.com", declarations)


def test_replace_omission_check_idempotence_and_absence():
    unmanaged = existing(name="other")
    provider = Provider([existing(), unmanaged])
    declarations = dns.validate("example.com", [entry()])
    assert dns.reconcile(declarations, provider.request, check=True)
    assert [c[0] for c in provider.calls] == ["GET"]
    provider.calls.clear()
    assert dns.reconcile(declarations, provider.request)
    assert [c[0] for c in provider.calls] == ["GET", "PUT", "DELETE"]
    assert unmanaged in provider.records
    assert not dns.reconcile(declarations, provider.request)
    absent = dns.validate(
        "example.com", [entry(state="absent", ttl="ignored", values=None)]
    )
    assert dns.reconcile(absent, provider.request)
    assert provider.records == [unmanaged]
    assert not dns.reconcile(absent, provider.request)


def test_pagination_and_chunking():
    provider = Provider([existing(name=f"host{i}") for i in range(501)])
    values = [f"192.0.{i // 256}.{i % 256}" for i in range(501)]
    assert dns.reconcile(
        dns.validate("example.com", [entry(values=values)]), provider.request
    )
    assert [c[1] for c in provider.calls[:2]] == [
        "?take=500&skip=0",
        "?take=500&skip=500",
    ]
    assert [len(c[2]["items"]) for c in provider.calls if c[0] == "PUT"] == [500, 1]


@pytest.mark.parametrize("group", ["product", "personalNs"])
def test_protected_groups(group):
    provider = Provider([existing(group={"type": group})])
    with pytest.raises(ValueError, match="provider-managed"):
        dns.reconcile(dns.validate("example.com", [entry()]), provider.request)
    assert [c[0] for c in provider.calls] == ["GET"]


def test_exclusive_replacement_and_stop_on_failure():
    record = dns.translate("www", "CNAME", 300, "old.example.net.")
    provider = Provider([dict(record, group={"type": "custom"})], fail="PUT")
    declarations = dns.validate(
        "example.com",
        [entry(type="CNAME", values=["new.example.net."]), entry(name="later")],
    )
    with pytest.raises(ValueError, match="simulated"):
        dns.reconcile(declarations, provider.request)
    assert [c[0] for c in provider.calls] == ["GET", "DELETE", "PUT"]
    assert provider.records == []
    provider.fail = None
    assert dns.reconcile(declarations, provider.request)
    assert not dns.reconcile(declarations, provider.request)


def test_case_and_txt_comparison():
    provider = Provider(
        [existing(type="CNAME", cname="TARGET.EXAMPLE.NET.", address="unused")]
    )
    assert not dns.reconcile(
        dns.validate(
            "example.com", [entry(type="CNAME", values=["target.example.net."])]
        ),
        provider.request,
    )
    provider = Provider([existing(type="TXT", value="CaseSensitive")])
    assert dns.reconcile(
        dns.validate("example.com", [entry(type="TXT", values=['"casesensitive"'])]),
        provider.request,
    )


@pytest.fixture
def spaceship_role(installed, tmp_path):
    provider = Provider()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            assert self.headers["X-API-Key"] in {"variable-key", "environment-key"}
            assert self.headers["X-API-Secret"] == "environment-secret"
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else None
            query = "?" + self.path.split("?", 1)[1] if "?" in self.path else ""
            try:
                result = provider.request(self.command, query, body)
            except ValueError:
                self.send_response(422)
                self.end_headers()
                return
            self.send_response(200 if self.command == "GET" else 204)
            self.end_headers()
            if result is not None:
                self.wfile.write(json.dumps(result).encode())

        do_GET = do_PUT = do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    module = (
        installed
        / "ansible_collections/madebyphunky/spaceship/plugins/modules/dns_records.py"
    )
    original = module.read_text()
    module.write_text(
        original.replace(
            "https://spaceship.dev/api", f"http://127.0.0.1:{server.server_port}/api"
        )
    )
    env = os.environ.copy() | {
        "ANSIBLE_COLLECTIONS_PATH": str(installed),
        "ANSIBLE_PYTHON_INTERPRETER": os.sys.executable,
        "SPACESHIP_API_KEY": "environment-key",
        "SPACESHIP_API_SECRET": "environment-secret",
        "ANSIBLE_NOCOLOR": "1",
    }

    def run(overrides=None, environment_only=False, **kwargs):
        variables = dict(
            spaceship_dns_zone="example.com", spaceship_dns_records=[entry()]
        )
        if not environment_only:
            variables["spaceship_dns_api_key"] = "variable-key"
        return invoke(
            variables | (overrides or {}),
            env=env,
            role="madebyphunky.spaceship.dns",
            **kwargs,
        )

    yield run, provider
    module.write_text(original)
    server.shutdown()
    server.server_close()
    thread.join()


def test_installed_role(spaceship_role):
    run, provider = spaceship_role
    prediction = run(check=True)
    assert prediction.returncode == 0, prediction.stdout
    assert changed(prediction) == 1
    assert not provider.records
    first = run(verbose=True)
    assert first.returncode == 0, first.stdout
    assert changed(first) == 1
    assert all(
        secret not in first.stdout for secret in ["variable-key", "environment-secret"]
    )
    again = run()
    assert again.returncode == 0, again.stdout
    assert changed(again) == 0
    deletion = run({"spaceship_dns_records": [entry(state="absent")]})
    assert deletion.returncode == 0, deletion.stdout
    assert provider.records == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"spaceship_dns_api_key": ""},
        {"spaceship_dns_api_secret": ""},
        {"spaceship_dns_records": [entry(), entry(name="WWW")]},
        {"spaceship_dns_records": [entry(), entry(name="later", values=["invalid"])]},
    ],
)
def test_installed_preflight_no_api_calls(spaceship_role, overrides):
    run, provider = spaceship_role
    result = run(overrides)
    assert result.returncode != 0
    assert provider.calls == []


def test_installed_environment_credentials(spaceship_role):
    run, provider = spaceship_role
    result = run(environment_only=True)
    assert result.returncode == 0, result.stdout
    assert provider.records


def test_installed_api_failure_retains_partial_progress(spaceship_role):
    run, provider = spaceship_role
    provider.records = [existing()]
    provider.fail = "DELETE"
    result = run(
        {"spaceship_dns_records": [entry(), entry(name="later")]}, verbose=True
    )
    assert result.returncode != 0
    assert '"changed": true' in result.stdout
    assert [c[0] for c in provider.calls] == ["GET", "PUT", "DELETE"]
    assert len(provider.records) == 2
    assert "environment-secret" not in result.stdout
    provider.fail = None
    recovery = run({"spaceship_dns_records": [entry(), entry(name="later")]})
    assert recovery.returncode == 0, recovery.stdout
    assert {r["name"] for r in provider.records} == {"www", "later"}


def test_optional_service_owner_representation():
    desired = dns.translate("_https.www", "HTTPS", 300, '1 . alpn="h2"')
    current = dict(desired, name="www", scheme="_https", group={"type": "custom"})
    assert dns.content_key(current) == dns.content_key(desired)
    provider = Provider([current])
    declarations = dns.validate(
        "example.com",
        [entry(name="_https.www", type="HTTPS", values=['1 . alpn="h2"'])],
    )
    assert not dns.reconcile(declarations, provider.request)
