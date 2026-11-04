#!/usr/bin/python
# Copyright: (c) 2026, madebyphunky
# MIT License (see LICENSE)
"""Ensure production-scoped Vercel Project environment variables."""

from __future__ import annotations

DOCUMENTATION = r"""
module: env
short_description: Ensure production environment variables on a Vercel Project
version_added: '0.3.0'
description:
  - Ensures declared application environment variables for the production target only.
  - Preview and development targets are refused.
  - Unspecified remote variables are preserved.
author:
  - madebyphunky
options:
  name:
    description: Explicit Vercel Project name.
    type: str
    required: true
  scope_type:
    description: Whether scope_id identifies a personal account or team.
    type: str
    choices: [personal, team]
    required: true
  scope_id:
    description: Expected Vercel account or team ID; verified before mutation.
    type: str
    required: true
  variables:
    description: Map of environment variable names to values.
    type: dict
    required: true
  target:
    description: Vercel environment target; must be production.
    type: str
    default: production
    choices: [production]
  vercel_token:
    description: Vercel bearer credential; normally supplied by the Role.
    type: str
    required: true
  timeout:
    description: Overall provider-operation budget, in seconds.
    type: int
    default: 900
  npx_executable:
    description: Path or command name for npx.
    type: str
    default: npx
  node_executable:
    description: Node executable whose directory should lead PATH for npm/npx shebangs.
    type: str
    default: node
attributes:
  check_mode:
    support: partial
    details: Reports a conservative plan without provider inspection or npx downloads.
"""
EXAMPLES = r"""
- name: Ensure production Application env vars
  madebyphunky.vercel.env:
    name: my-project
    scope_type: team
    scope_id: team_example
    vercel_token: "{{ VERCEL_TOKEN }}"
    variables:
      NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co"
      SUPABASE_SECRET_KEY: "{{ vault_secret }}"
"""
RETURN = r"""
result:
  description: Sanitized Project identity and ensured variable names.
  returned: always
  type: dict
"""

import json
import os
import re
import signal
import subprocess
import tempfile
import time
from urllib.parse import quote, urlencode

from ansible.module_utils.basic import AnsibleModule


class ProviderError(Exception):
    """A redacted provider or contract failure."""


class Environment:
    def __init__(self, module):
        self.module = module
        self.p = module.params
        self.deadline = time.monotonic() + self.p["timeout"]
        self.changed = False
        self.result = {
            "project": None,
            "ensured": [],
            "created": [],
            "updated": [],
            "actions": [],
            "inspection_limited": False,
        }
        self.directory = None

    def fail(self, message):
        raise ProviderError(message)

    def validate(self):
        p = self.p
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", p["name"]):
            self.fail(
                "Use a lowercase Project name with at most 100 letters, digits, and internal hyphens"
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]+", p["scope_id"]):
            self.fail("Supply an explicit account/team ID")
        if not p["vercel_token"].strip():
            self.fail("Supply VERCEL_TOKEN")
        if p["timeout"] < 1:
            self.fail("Timeout must be a positive integer")
        if p["target"] != "production":
            self.fail("Only the production environment target is supported")
        variables = p["variables"] or {}
        if not isinstance(variables, dict) or not variables:
            self.fail("Supply at least one environment variable")
        for key, value in variables.items():
            if not isinstance(key, str) or not key.strip():
                self.fail("Environment variable names must be nonblank strings")
            if value is None or not isinstance(value, str) or value == "":
                self.fail("Environment variable values must be nonblank strings")

    def redacted(self, text):
        text = text.replace(self.p["vercel_token"], "<redacted>")
        for value in (self.p.get("variables") or {}).values():
            if value:
                text = text.replace(str(value), "<redacted>")
        return text

    def command(self, argv, data=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.fail("Provider-operation timeout exceeded; resources are retained")
        env = os.environ.copy()
        env.update(
            {
                "CI": "1",
                "NO_COLOR": "1",
                "VERCEL_TELEMETRY_DISABLED": "1",
                "VERCEL_ORG_ID": "",
                "VERCEL_PROJECT_ID": "",
                "VERCEL_TEAM_ID": "",
                "NPM_CONFIG_UPDATE_NOTIFIER": "false",
                "VERCEL_TOKEN": self.p["vercel_token"],
            }
        )
        node_directory = os.path.dirname(self.p["node_executable"])
        if node_directory:
            env["PATH"] = node_directory + os.pathsep + env.get("PATH", "")
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.directory,
                env=env,
                start_new_session=True,
            )
            try:
                out, err = process.communicate(data, timeout=min(remaining, 120))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                self.fail("CLI request timed out; resources are retained")
        except OSError as error:
            self.fail("Cannot execute required client: " + self.redacted(str(error)))
        return process.returncode, out, err

    def request(self, path, method="GET", body=None, missing=False):
        if self.p["scope_type"] == "team" and not path.startswith("/v2/"):
            path += ("&" if "?" in path else "?") + urlencode(
                {"teamId": self.p["scope_id"]}
            )
        argv = [
            self.p["npx_executable"],
            "--yes",
            "vercel@latest",
            "api",
            path,
            "--method",
            method,
            "--raw",
            "--include",
            "--non-interactive",
            "--global-config",
            self.directory,
        ]
        if body is not None:
            argv.extend(["--input", "-"])
        rc, out, err = self.command(
            argv, json.dumps(body) if body is not None else None
        )
        status_match = re.search(r"HTTP/\S+\s+(\d{3})", out)
        status = int(status_match.group(1)) if status_match else None
        positions = [index for index in (out.find("{"), out.find("[")) if index >= 0]
        response = None
        if positions:
            try:
                response = json.loads(out[min(positions) :].strip())
            except ValueError:
                self.fail("Provider returned an invalid JSON response")
        error = response.get("error") if isinstance(response, dict) else None
        if missing and (status == 404 or (rc and re.search(r"HTTP 404|\(404\)", err))):
            return None
        if rc or (status and status >= 400) or error:
            message = (
                error.get("message", str(error))
                if isinstance(error, dict)
                else err.strip()
            )
            if not message and isinstance(response, dict):
                message = response.get("message", "")
            self.fail(
                "vercel API {} {} failed{}: {}".format(
                    method,
                    path,
                    " (HTTP " + str(status) + ")" if status else "",
                    self.redacted(message or "request rejected")[:1000],
                )
            )
        return response or {}

    def action(self, name):
        self.changed = True
        self.result["actions"].append(name)

    def variable_type(self, key):
        return "encrypted" if key.startswith("NEXT_PUBLIC_") else "sensitive"

    def list_envs(self, project_id):
        response = self.request("/v10/projects/" + quote(project_id, safe="") + "/env")
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            envs = response.get("envs")
            if isinstance(envs, list):
                return envs
        self.fail("Unsupported Vercel environment variable list response")

    def production_env(self, rows, key):
        matches = [
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("key") == key
            and "production" in (row.get("target") or [])
        ]
        return matches[0] if matches else None

    def ensure(self):
        self.validate()
        if self.module.check_mode:
            self.result.update(
                inspection_limited=True,
                plan="CLI inspection deferred to avoid downloads in check mode",
            )
            self.changed = True
            return
        with tempfile.TemporaryDirectory(prefix="ansible-vercel-env-") as directory:
            self.directory = directory
            if self.p["scope_type"] == "personal":
                user = self.request("/v2/user")
                actual = (user.get("user") or {}).get("id")
            else:
                team = self.request("/v2/teams/" + quote(self.p["scope_id"], safe=""))
                actual = team.get("id")
            if actual != self.p["scope_id"]:
                self.fail("Returned account/team ID does not match the explicit scope")
            project = self.request(
                "/v9/projects/" + quote(self.p["name"], safe=""), missing=True
            )
            if project is None:
                self.fail("Vercel Project does not exist; create it before setting env")
            if project.get("name") != self.p["name"]:
                self.fail(
                    "Returned Project name does not match the explicit Project identity"
                )
            if project.get("accountId") != self.p["scope_id"]:
                self.fail(
                    "Returned Project owner does not match the explicit account/team ID"
                )
            self.result["project"] = {
                "id": project.get("id"),
                "name": project.get("name"),
                "account_id": project.get("accountId"),
            }
            rows = self.list_envs(project["id"])
            for key, value in self.p["variables"].items():
                var_type = self.variable_type(key)
                existing = self.production_env(rows, key)
                payload = {
                    "key": key,
                    "value": value,
                    "type": var_type,
                    "target": ["production"],
                }
                if existing is None:
                    self.request(
                        "/v10/projects/" + quote(project["id"], safe="") + "/env",
                        method="POST",
                        body=payload,
                    )
                    self.action("create:" + key)
                    self.result["created"].append(key)
                    rows.append(payload | {"id": "created-" + key})
                else:
                    remote_value = existing.get("value")
                    if remote_value is None and existing.get("type") == "sensitive":
                        # Sensitive values are not readable; leave unchanged for idempotency.
                        self.result["ensured"].append(key)
                        continue
                    if remote_value == value and existing.get("type") == var_type:
                        self.result["ensured"].append(key)
                        continue
                    self.request(
                        "/v9/projects/"
                        + quote(project["id"], safe="")
                        + "/env/"
                        + quote(existing["id"], safe=""),
                        method="PATCH",
                        body={
                            "value": value,
                            "type": var_type,
                            "target": ["production"],
                        },
                    )
                    self.action("update:" + key)
                    self.result["updated"].append(key)
                self.result["ensured"].append(key)


def main():
    module = AnsibleModule(
        argument_spec={
            "name": {"type": "str", "required": True},
            "scope_type": {
                "type": "str",
                "required": True,
                "choices": ["personal", "team"],
            },
            "scope_id": {"type": "str", "required": True},
            "variables": {"type": "dict", "required": True, "no_log": True},
            "target": {
                "type": "str",
                "default": "production",
                "choices": ["production"],
            },
            "vercel_token": {"type": "str", "required": True, "no_log": True},
            "timeout": {"type": "int", "default": 900},
            "npx_executable": {"type": "str", "default": "npx"},
            "node_executable": {"type": "str", "default": "node"},
        },
        supports_check_mode=True,
    )
    operation = Environment(module)
    try:
        operation.ensure()
    except ProviderError as exc:
        module.fail_json(
            msg=str(exc),
            changed=operation.changed,
            result=operation.result,
        )
    module.exit_json(
        changed=operation.changed,
        result=operation.result,
    )


if __name__ == "__main__":
    main()
