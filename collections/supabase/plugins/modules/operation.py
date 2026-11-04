#!/usr/bin/python
# Copyright: (c) 2026, madebyphunky
# MIT License (see LICENSE)
"""CLI boundary shared by the public hosted Supabase Roles."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import tempfile
import time

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
module: operation
short_description: Run a scoped hosted Supabase CLI operation
version_added: '0.1.0'
description:
  - Internal CLI boundary used by the public project, auth, migrations, and credentials Roles.
  - Requires Python 3.11 or later for TOML configuration parsing.
  - Check mode validates locally without invoking npx or downloading packages.
author: [madebyphunky]
options:
  operation:
    description: Public Role operation.
    type: str
    required: true
    choices: [project, auth, migrations, credentials]
  access_token:
    description: Supabase access token.
    type: str
    required: true
  db_password:
    description: Explicit creation password or required migrations password; never rotates existing Projects.
    type: str
  organization:
    description: Explicit organization slug or ID.
    type: str
  name:
    description: Exact Project name.
    type: str
  region:
    description: Region for creation and existing-region verification.
    type: str
  project_ref:
    description: Exact Project reference.
    type: str
  config_path:
    description: Existing TOML file supplying Auth settings.
    type: path
  workdir:
    description: Application checkout containing supabase/migrations.
    type: path
  cli_version:
    description: npm CLI version or tag.
    type: str
    default: latest
  npx_executable:
    description: npx executable.
    type: str
    default: npx
  node_executable:
    description: Node executable whose directory leads PATH.
    type: str
    default: node
  timeout:
    description: Overall execution budget in seconds.
    type: int
    default: 900
  poll_interval:
    description: Readiness polling interval in seconds.
    type: int
    default: 5
  validate_only:
    description: Validate local inputs before prerequisite installation.
    type: bool
    default: false
attributes:
  check_mode:
    support: partial
    details: Conservative plan; no CLI execution or downloads.
"""
EXAMPLES = r"""
- name: Ensure a hosted Project through the public Role
  ansible.builtin.include_role:
    name: madebyphunky.supabase.project
  vars:
    supabase_organization: my-organization
    supabase_project_name: my-project
    supabase_region: eu-west-2
    supabase_project_password: "{{ vault_supabase_password }}"
"""
RETURN = r"""
result:
  description: Nonsecret project identity and operation summary.
  type: dict
  returned: always
"""


class CliError(Exception):
    """A failure whose message cannot contain provider output or credentials."""


PROJECT_REF = re.compile(r"^[a-z]{20}$")


def require_project_ref(value):
    if not PROJECT_REF.fullmatch(value or ""):
        raise CliError(
            "Supply an exact 20-character lowercase Supabase Project reference"
        )
    return value


def content_paths(value, prefix=()):
    """Yield Auth content_path values as (toml_path_tuple, relative_path)."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from content_paths(item, prefix + (key,))
    elif prefix and prefix[-1] == "content_path":
        if not isinstance(value, str) or not value.strip():
            raise CliError("Auth content_path values must be nonblank strings")
        yield prefix, value


def toml_value(value):
    """Encode parsed TOML values without evaluating strings or retaining other sections."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(json.dumps(k) + " = " + toml_value(v) for k, v in value.items())
            + "}"
        )
    raise CliError("Unsupported TOML value in Auth configuration")


def auth_toml(auth):
    # Dotted keys retain the exact Auth tree, including provider-specific sections.
    lines = []

    def visit(prefix, fields):
        for key, value in fields.items():
            path = prefix + [key]
            if isinstance(value, dict) and value:
                visit(path, value)
            else:
                lines.append(
                    ".".join(json.dumps(k) for k in path) + " = " + toml_value(value)
                )

    visit(["auth"], auth)
    return "\n".join(lines) + "\n"


class Supabase:
    def __init__(self, module):
        self.module = module
        self.p = module.params
        self.result = {
            "operation": self.p["operation"],
            "project": None,
            "inspection_limited": False,
        }
        self.changed = False
        self.deadline = time.monotonic() + self.p["timeout"]
        self.auth = None
        self.auth_config_path = None
        self.directory = None

    def validate(self):
        p = self.p
        if not p["access_token"].strip():
            raise CliError("Supply SUPABASE_ACCESS_TOKEN")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", p["cli_version"]):
            raise CliError("Supply a Supabase npm version or tag")
        if p["timeout"] < 1 or p["poll_interval"] < 1:
            raise CliError("Timeout and poll interval must be positive")
        if p["operation"] == "project":
            if not (p["organization"] or "").strip() or not (p["name"] or "").strip():
                raise CliError("Supply explicit organization and Project name")
            if p["db_password"] is not None and not p["db_password"].strip():
                raise CliError(
                    "supabase_project_password must be nonblank when supplied"
                )
            if p["project_ref"] is not None:
                require_project_ref(p["project_ref"])
        else:
            require_project_ref(p["project_ref"])
        if p["operation"] == "auth":
            try:
                import tomllib
            except ImportError:
                raise CliError("Auth requires Python 3.11 or later") from None
            try:
                self.auth_config_path = Path(p["config_path"] or "").resolve()
                with open(self.auth_config_path, "rb") as stream:
                    config = tomllib.load(stream)
            except (OSError, ValueError):
                raise CliError(
                    "Cannot read a valid Supabase Auth config.toml"
                ) from None
            self.auth = config.get("auth")
            if not isinstance(self.auth, dict) or not self.auth:
                raise CliError("Supply at least one explicit Auth setting")
            for _, relative in content_paths(self.auth):
                self.resolve_content_source(relative)
        if p["operation"] == "migrations":
            if not (p["db_password"] or "").strip():
                raise CliError("Supply SUPABASE_DB_PASSWORD for migrations")
            source = Path(p["workdir"] or "") / "supabase" / "migrations"
            if not source.is_dir():
                raise CliError("Application checkout must contain supabase/migrations")

    def resolve_content_source(self, relative):
        """Locate a declared Auth content_path under the caller's config roots."""
        if Path(relative).is_absolute():
            raise CliError("Auth content_path values must be relative paths")
        config_dir = self.auth_config_path.parent.resolve()
        project_root = config_dir.parent
        for root, under_supabase in ((project_root, False), (config_dir, True)):
            source = (root / relative).resolve()
            if not source.is_file() or (
                root not in source.parents and source.parent != root
            ):
                continue
            return source, under_supabase
        raise CliError("Auth content_path file is missing: " + relative)

    def stage_auth_files(self):
        """Stage Auth-only TOML plus any referenced email-template content files."""
        workdir = Path(self.directory).resolve()
        (workdir / "supabase" / "config.toml").write_text(auth_toml(self.auth))
        for _, relative in content_paths(self.auth):
            source, under_supabase = self.resolve_content_source(relative)
            destination = (
                workdir / "supabase" / relative
                if under_supabase
                else workdir / relative
            ).resolve()
            if workdir not in destination.parents:
                raise CliError("Auth content_path escapes the isolated workdir")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def cli(self, args, allowed=(0,)):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise CliError(
                "Supabase operation timed out; existing resources were retained"
            )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SUPABASE_")
        }
        # Explicit credentials override ambient CLI credentials. Never use saved login identity.
        env.update(
            SUPABASE_ACCESS_TOKEN=self.p["access_token"],
            SUPABASE_HOME=str(Path(self.directory) / ".cli-home"),
            CI="true",
            NO_COLOR="1",
        )
        env.pop("SUPABASE_DB_PASSWORD", None)
        if self.p["db_password"]:
            env["SUPABASE_DB_PASSWORD"] = self.p["db_password"]
        node = shutil.which(self.p["node_executable"])
        if node:
            env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
        command = [
            self.p["npx_executable"],
            "--yes",
            "supabase@" + self.p["cli_version"],
        ] + args
        try:
            process = subprocess.Popen(
                command,
                cwd=self.directory,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                output, _ = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise CliError(
                    "Supabase CLI timed out; inspect the retained Project before retrying"
                ) from None
        except OSError:
            raise CliError(
                "Cannot execute npx; supply working Node.js/npx prerequisites"
            ) from None
        if process.returncode not in allowed:
            # CLI output may contain SQL, Auth secrets, passwords, or connection strings.
            raise CliError(
                "Supabase CLI "
                + " ".join(args[:2])
                + " failed (exit "
                + str(process.returncode)
                + "); provider output suppressed to protect secrets"
            )
        return output, process.returncode

    def json_cli(self, args):
        output, _ = self.cli(args + ["-o", "json"])
        try:
            return json.loads(output)
        except ValueError:
            raise CliError(
                "Supabase CLI returned an unsupported JSON response"
            ) from None

    def projects(self):
        rows = self.json_cli(["projects", "list"])
        if not isinstance(rows, list):
            raise CliError("Supabase CLI returned an unsupported Project list")
        return rows

    @staticmethod
    def ref(row):
        return row.get("ref") or row.get("id")

    def publish_project(self, row):
        self.result["project"] = {
            key: row.get(key)
            for key in (
                "name",
                "region",
                "status",
                "organization_id",
                "organization_slug",
            )
            if key in row
        }
        self.result["project"]["ref"] = self.ref(row)
        self.result["project"]["url"] = "https://" + self.ref(row) + ".supabase.co"

    def project(self):
        p = self.p
        orgs = self.json_cli(["orgs", "list"])
        if not isinstance(orgs, list):
            raise CliError("Supabase CLI returned an unsupported organization list")
        orgs = [
            row for row in orgs if p["organization"] in (row.get("id"), row.get("slug"))
        ]
        if len(orgs) != 1:
            raise CliError(
                "Explicit organization must resolve to exactly one accessible organization"
            )
        org = orgs[0]
        identifiers = {value for value in (org.get("id"), org.get("slug")) if value}
        rows = self.projects()
        if p["project_ref"]:
            matches = [row for row in rows if self.ref(row) == p["project_ref"]]
            if len(matches) != 1:
                raise CliError(
                    "Explicit Project reference must resolve to an existing Project"
                )
            row = matches[0]
            if not identifiers.intersection(
                (row.get("organization_id"), row.get("organization_slug"))
            ):
                raise CliError("Project reference belongs to a different organization")
            if row.get("name") != p["name"]:
                raise CliError(
                    "Explicit Project reference has a different name; refusing to rename"
                )
        else:
            matches = [
                row
                for row in rows
                if row.get("name") == p["name"]
                and identifiers.intersection(
                    (row.get("organization_id"), row.get("organization_slug"))
                )
            ]
            if len(matches) > 1:
                raise CliError(
                    "Multiple Projects match the exact organization and name; supply a reference"
                )
            row = matches[0] if matches else None
        if row and p["region"] and row.get("region") != p["region"]:
            raise CliError(
                "Existing Project region differs; refusing to recreate or move it"
            )
        if row is None:
            if not (p["region"] or "").strip():
                raise CliError("An explicit region is required to create a Project")
            if p["db_password"] is None:
                raise CliError("Supply supabase_project_password to create a Project")
            self.result["creation_attempted"] = True
            # An indeterminate creation is never retried automatically.
            self.changed = True
            created = self.json_cli(
                [
                    "projects",
                    "create",
                    p["name"],
                    "--org-id",
                    org.get("slug") or org["id"],
                    "--region",
                    p["region"],
                    "--db-password",
                    p["db_password"],
                    "--yes",
                ]
            )
            if not isinstance(created, dict) or not self.ref(created):
                raise CliError(
                    "Creation returned no Project reference; inspect the organization before retrying"
                )
            row = created
            self.publish_project(row)
        else:
            self.publish_project(row)
        while row.get("status") != "ACTIVE_HEALTHY":
            if time.monotonic() + p["poll_interval"] >= self.deadline:
                raise CliError(
                    "Project readiness timed out; Project retained for inspection"
                )
            if row.get("status") in (
                "REMOVED",
                "GOING_DOWN",
                "RESTORE_FAILED",
                "INIT_FAILED",
            ):
                raise CliError("Project is not available; inspect it in Supabase")
            time.sleep(p["poll_interval"])
            matches = [
                item
                for item in self.projects()
                if self.ref(item) == self.result["project"]["ref"]
            ]
            if len(matches) != 1:
                raise CliError("Project disappeared during readiness inspection")
            row = matches[0]
            self.publish_project(row)

    def auth_config(self):
        self.stage_auth_files()
        output, _ = self.cli(
            [
                "config",
                "diff",
                "--remote=" + self.p["project_ref"],
                "--output-format",
                "json",
                "--exit-code",
            ],
            allowed=(0, 2),
        )
        try:
            diff = json.loads(output)
            if (
                diff.get("schema_version") != 1
                or diff.get("target", {}).get("project_ref") != self.p["project_ref"]
            ):
                raise CliError("Unexpected CLI config diff schema or target")
            pending = any(
                change.get("declared") is True
                and change.get("path", [None])[0] == "auth"
                and change.get("class") in ("update", "local_only")
                for change in diff["changes"]
            )
            masked = [path for path in diff["masked"] if path and path[0] == "auth"]
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            raise CliError(
                "Unsupported CLI config diff response; refusing to push blindly"
            ) from None
        self.result["project"] = {"ref": self.p["project_ref"]}
        missing_auth = any(
            service == "auth" or service.startswith("auth.")
            for service in diff.get("scope", {}).get("missing", [])
        )
        if diff.get("unmanaged") or missing_auth:
            raise CliError(
                "CLI cannot inspect all requested Auth settings; refusing to report convergence"
            )
        if pending or masked:
            self.changed = True  # A failing push may have partially applied settings.
            output, _ = self.cli(
                [
                    "config",
                    "push",
                    "--remote=" + self.p["project_ref"],
                    "--yes",
                    "--output-format",
                    "json",
                ]
            )
            try:
                pushed = json.loads(output)
                if (
                    pushed.get("schema_version") != 1
                    or pushed.get("project_ref") != self.p["project_ref"]
                ):
                    raise ValueError()
                services = [
                    item for item in pushed["services"] if item["service"] == "auth"
                ]
                if not services or any(
                    item["status"] not in ("updated", "up_to_date") for item in services
                ):
                    raise CliError("CLI could not apply requested Auth settings")
                secret_results = pushed.get("secrets", {})
                if any(
                    pushed.get(key)
                    for key in ("unsupported", "unencodable", "unmanaged")
                ) or any(
                    secret_results.get(key)
                    for key in ("not_set", "gated", "unencodable", "skipped")
                ):
                    raise CliError(
                        "CLI did not apply all requested Auth settings or secrets"
                    )
                self.changed = any(
                    item["status"] == "updated" for item in services
                ) or bool(secret_results.get("sent"))
            except (ValueError, KeyError, TypeError, AttributeError):
                raise CliError(
                    "Unsupported CLI config push response; inspect retained Project"
                ) from None
        self.result["configuration_changed"] = self.changed

    def migrations(self):
        source = Path(self.p["workdir"]) / "supabase" / "migrations"
        shutil.copytree(source, Path(self.directory) / "supabase" / "migrations")
        (Path(self.directory) / "supabase" / "config.toml").write_text(
            "[db.migrations]\nenabled = true\n"
        )
        args = ["db", "push", "--remote=" + self.p["project_ref"], "--skip-vault"]
        output, _ = self.cli(args + ["--dry-run", "--output-format", "json"])
        self.result["project"] = {"ref": self.p["project_ref"]}
        try:
            plan = json.loads(output)
            if not isinstance(plan["upToDate"], bool) or not isinstance(
                plan["migrations"], list
            ):
                raise ValueError()
            if plan.get("target", {}).get("project_ref") != self.p["project_ref"]:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise CliError(
                "Unsupported CLI migration dry-run response; refusing to push blindly"
            ) from None
        if plan["migrations"]:
            self.changed = True
            self.cli(args + ["--yes", "--output-format", "json"])
        elif not plan["upToDate"]:
            raise CliError(
                "CLI reports pending non-migration changes; refusing to push blindly"
            )
        self.result["migrations_applied"] = self.changed

    def select_api_key(self, rows, preferred_type, legacy_name):
        preferred = [
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("type") == preferred_type
            and (row.get("api_key") or "").strip()
        ]
        preferred.sort(key=lambda row: 0 if row.get("name") == "default" else 1)
        if preferred:
            return preferred[0]["api_key"]
        legacy = [
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("type") == "legacy"
            and row.get("name") == legacy_name
            and (row.get("api_key") or "").strip()
        ]
        if legacy:
            return legacy[0]["api_key"]
        return None

    def credentials(self):
        ref = self.p["project_ref"]
        rows = self.json_cli(
            ["projects", "api-keys", "--project-ref", ref, "--reveal"]
        )
        if not isinstance(rows, list):
            raise CliError("Unsupported CLI API key response")
        publishable = self.select_api_key(rows, "publishable", "anon")
        secret = self.select_api_key(rows, "secret", "service_role")
        if not publishable or not secret:
            raise CliError(
                "Project API keys must include a publishable key and a secret key"
            )
        self.result["project"] = {
            "ref": ref,
            "url": "https://" + ref + ".supabase.co",
        }
        self.result["publishable_key"] = publishable
        self.result["secret_key"] = secret
        self.changed = False

    def run(self):
        self.validate()
        if self.p["validate_only"]:
            return
        if self.module.check_mode:
            self.result.update(
                inspection_limited=True,
                plan="CLI inspection deferred to avoid downloads in check mode",
            )
            self.changed = True
            return
        with tempfile.TemporaryDirectory(prefix="ansible-supabase-") as directory:
            self.directory = directory
            Path(directory, "supabase").mkdir()
            if self.p["operation"] == "project":
                self.project()
            elif self.p["operation"] == "auth":
                self.auth_config()
            elif self.p["operation"] == "migrations":
                self.migrations()
            else:
                self.credentials()


def main():
    module = AnsibleModule(
        argument_spec={
            "operation": {
                "type": "str",
                "required": True,
                "choices": ["project", "auth", "migrations", "credentials"],
            },
            "access_token": {"type": "str", "required": True, "no_log": True},
            "db_password": {"type": "str", "no_log": True},
            **{
                key: {"type": "str"}
                for key in ("organization", "name", "region", "project_ref")
            },
            **{key: {"type": "path"} for key in ("config_path", "workdir")},
            "cli_version": {"type": "str", "default": "latest"},
            "npx_executable": {"type": "str", "default": "npx"},
            "node_executable": {"type": "str", "default": "node"},
            "timeout": {"type": "int", "default": 900},
            "poll_interval": {"type": "int", "default": 5},
            "validate_only": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    operation = Supabase(module)
    try:
        operation.run()
    except (CliError, OSError) as exc:
        message = (
            str(exc)
            if isinstance(exc, CliError)
            else "Cannot read or stage local Supabase files"
        )
        module.fail_json(
            msg=message,
            changed=operation.changed,
            result=operation.result,
        )
    module.exit_json(
        changed=operation.changed,
        result=operation.result,
    )


if __name__ == "__main__":
    main()
