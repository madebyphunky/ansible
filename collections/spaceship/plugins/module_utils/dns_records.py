"""Translate DNS presentation values and reconcile explicitly owned RRsets."""

import ipaddress
import json
import re

import dns.name
import dns.rdata

TYPES = {
    "A",
    "AAAA",
    "ALIAS",
    "CAA",
    "CNAME",
    "HTTPS",
    "MX",
    "NS",
    "PTR",
    "SRV",
    "SVCB",
    "TLSA",
    "TXT",
}
FIELDS = {
    "A": ["address"],
    "AAAA": ["address"],
    "ALIAS": ["aliasName"],
    "CAA": ["flag", "tag", "value"],
    "CNAME": ["cname"],
    "HTTPS": ["svcPriority", "targetName", "svcParams"],
    "MX": ["preference", "exchange"],
    "NS": ["nameserver"],
    "PTR": ["pointer"],
    "SRV": ["priority", "weight", "port", "target"],
    "SVCB": ["svcPriority", "targetName", "svcParams"],
    "TLSA": ["usage", "selector", "matching", "associationData"],
    "TXT": ["value"],
}


def owner(record):
    """Recover the complete relative owner from Spaceship's split labels."""
    labels = []
    kind = record["type"]
    if kind == "SRV":
        labels = [record["service"], record["protocol"]]
    elif kind == "TLSA":
        labels = [record["port"], record["protocol"]]
    elif kind in {"HTTPS", "SVCB"}:
        labels = [record[k] for k in ("port", "scheme") if record.get(k)]
    name = record["name"]
    return ".".join(labels + ([] if name == "@" else [name])).lower() or "@"


def split_owner(name, kind):
    result = {"name": name.lower()}
    parts = name.lower().split(".")
    keys = []
    if kind == "SRV":
        keys = ["service", "protocol"]
    elif kind == "TLSA":
        keys = ["port", "protocol"]
    elif (
        kind in {"HTTPS", "SVCB"}
        and len(parts) >= 2
        and (parts[0].startswith("_") or parts[0] == "*")
        and parts[1].startswith("_")
    ):
        keys = ["port", "scheme"]
    if keys:
        if len(parts) < 2 or any(
            not re.fullmatch(r"_[a-z0-9-]+|\*", p) for p in parts[:2]
        ):
            raise ValueError(
                f"{kind} requires service/port and protocol labels in name"
            )
        result.update(zip(keys, parts[:2]))
        result["name"] = ".".join(parts[2:]) or "@"
    return result


def translate(name, kind, ttl, value):
    r = dns.rdata.from_text(
        "IN",
        "CNAME" if kind == "ALIAS" else kind,
        value,
        origin=dns.name.root,
        relativize=False,
    )
    result = {"type": kind, "ttl": ttl, **split_owner(name, kind)}

    def host(v):
        return v.to_text().rstrip(".") or "."

    if kind in {"A", "AAAA"}:
        data = {"address": r.address}
    elif kind in {"CNAME", "ALIAS", "NS", "PTR"}:
        attr = {"CNAME": "target", "ALIAS": "target", "NS": "target", "PTR": "target"}[
            kind
        ]
        data = {FIELDS[kind][0]: host(getattr(r, attr))}
    elif kind == "MX":
        data = {"preference": r.preference, "exchange": host(r.exchange)}
    elif kind == "TXT":
        data = {"value": b"".join(r.strings).decode("utf-8")}
    elif kind == "CAA":
        data = {"flag": r.flags, "tag": r.tag.decode(), "value": r.value.decode()}
    elif kind == "SRV":
        data = {k: getattr(r, k) for k in ("priority", "weight", "port")}
        data["target"] = host(r.target)
    elif kind == "TLSA":
        data = {
            "usage": r.usage,
            "selector": r.selector,
            "matching": r.mtype,
            "associationData": r.cert.hex(),
        }
    else:
        text = r.to_text().split(None, 2)
        data = {
            "svcPriority": r.priority,
            "targetName": host(r.target),
            "svcParams": text[2] if len(text) == 3 else "",
        }
    result.update(data)
    return result


def validate(zone, entries):
    if (
        not isinstance(zone, str)
        or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", zone)
        or ".." in zone
    ):
        raise ValueError("Supply one zone without a trailing dot")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Supply a nonempty records list")
    seen, declarations = set(), []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {
            "name",
            "type",
            "state",
            "ttl",
            "values",
        }:
            raise ValueError("Record declarations must contain only supported fields")
        name, kind, state = (
            entry.get("name"),
            entry.get("type"),
            entry.get("state", "present"),
        )
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"@|(?:\*|[a-zA-Z0-9_-]+)(?:\.[a-zA-Z0-9_-]+)*", name)
            or name.lower() == zone.lower()
            or name.lower().endswith("." + zone.lower())
        ):
            raise ValueError("Use a relative record name or @")
        if kind not in TYPES or state not in {"present", "absent"}:
            raise ValueError("Unsupported record type or state")
        identity = (name.lower(), kind)
        if identity in seen:
            raise ValueError("Each name/type must be declared exactly once")
        seen.add(identity)
        desired = []
        if state == "present":
            ttl, values = entry.get("ttl"), entry.get("values")
            if type(ttl) is not int or not 60 <= ttl <= 3600:
                raise ValueError(
                    "Present TTL must be an integer between 60 and 3600 seconds"
                )
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(v, str) for v in values)
            ):
                raise ValueError(
                    "Present values must be a nonempty list of DNS-format strings"
                )
            desired = [translate(name, kind, ttl, value) for value in values]
            if kind in {"CNAME", "ALIAS"} and len(desired) != 1:
                raise ValueError("CNAME and ALIAS require exactly one value")
            if len({content_key(r) for r in desired}) != len(desired):
                raise ValueError("Duplicate record values are not supported")
        declarations.append((identity, desired))
    return declarations


def payload(record, delete=False):
    keys = ["type", "name"] + FIELDS[record["type"]]
    if record["type"] == "SRV":
        keys += ["service", "protocol"]
    elif record["type"] == "TLSA":
        keys += ["port", "protocol"]
    elif record["type"] in {"HTTPS", "SVCB"}:
        keys += [k for k in ("port", "scheme") if k in record]
    if not delete:
        keys += ["ttl"]
    return {k: record[k] for k in keys}


def content_key(record):
    data = payload(record, delete=True)
    for k, value in data.items():
        if isinstance(value, str) and not (record["type"] == "TXT" and k == "value"):
            data[k] = value.lower()
            if k in {
                "cname",
                "aliasName",
                "exchange",
                "nameserver",
                "pointer",
                "target",
                "targetName",
            }:
                data[k] = data[k].rstrip(".") or "."
    if record["type"] in {"A", "AAAA"}:
        data["address"] = str(ipaddress.ip_address(data["address"]))
    if record["type"] in {"HTTPS", "SVCB"}:
        r = dns.rdata.from_text(
            "IN",
            record["type"],
            f"{record['svcPriority']} {record['targetName']} {record['svcParams']}",
            origin=dns.name.root,
            relativize=False,
        )
        data["svcParams"] = r.to_text().lower().split(None, 2)[2:] or [""]
    if record["type"] == "TLSA":
        data["associationData"] = "".join(data["associationData"].split())
    # Compare complete owner names, independent of optional API label splitting.
    data["name"] = owner(record)
    if record["type"] == "SRV":
        for field in ("service", "protocol"):
            data.pop(field, None)
    elif record["type"] in {"TLSA", "HTTPS", "SVCB"}:
        for field in ("port", "protocol", "scheme"):
            data.pop(field, None)
    return json.dumps(data, sort_keys=True)


def reconcile(declarations, request, check=False):
    records, skip = [], 0
    while True:
        page = request("GET", f"?take=500&skip={skip}", None)
        items = page["items"]
        records.extend(items)
        skip += len(items)
        if skip >= page["total"]:
            break
        if not items:
            raise ValueError("Incomplete DNS pagination; refusing to mutate")
    changed = False
    for (name, kind), desired in declarations:
        current = [r for r in records if r["type"] == kind and owner(r) == name]
        # A CNAME cannot coexist with other types at its owner. Never prune those.
        conflicts = [
            r
            for r in records
            if owner(r) == name
            and r["type"] != kind
            and (kind == "CNAME" or r["type"] == "CNAME")
        ]
        if any(r.get("group", {}).get("type") != "custom" for r in current) or (
            desired and conflicts
        ):
            raise ValueError(
                f"Conflicting or provider-managed records at {name}/{kind}; no force allowed"
            )
        old = {content_key(r): r for r in current}
        new = {content_key(r): r for r in desired}
        remove = [r for key, r in old.items() if key not in new]
        save = [
            r
            for key, r in new.items()
            if key not in old or old[key].get("ttl") != r["ttl"]
        ]
        operations = [("PUT", save), ("DELETE", remove)]
        if kind in {"CNAME", "ALIAS"}:
            operations.reverse()
        for method, items in operations:
            if items:
                changed = True
            for offset in range(0, len(items), 500):
                batch = [
                    payload(r, delete=method == "DELETE")
                    for r in items[offset : offset + 500]
                ]
                if not check:
                    request(
                        method,
                        "",
                        {"force": False, "items": batch} if method == "PUT" else batch,
                    )
        records = [
            r for r in records if not (r["type"] == kind and owner(r) == name)
        ] + [dict(r, group={"type": "custom"}) for r in desired]
    return changed
