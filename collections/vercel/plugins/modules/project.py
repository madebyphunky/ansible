#!/usr/bin/python
# Copyright: (c) 2026, madebyphunky
# MIT License (see LICENSE)
"""Converge a Vercel Project through explicit, noninteractive CLI API calls."""

from __future__ import annotations

DOCUMENTATION = r"""
module: project
short_description: Converge a Vercel Project and optional production Deployment
version_added: '0.2.0'
description:
  - Manages explicitly scoped Vercel Projects using npx and the Vercel CLI API.
  - The public project Role composes tool prerequisites and calls this module.
  - Check mode reports a conservative plan without invoking npx or downloading packages.
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
  source_mode:
    description: No Git source, an existing repository, or ensure a repository exists.
    type: str
    choices: [none, existing, ensure]
    default: none
  github_owner:
    description: Explicit GitHub owner for Git source modes.
    type: str
  github_repository:
    description: Explicit GitHub repository name for Git source modes.
    type: str
  vercel_token:
    description: Vercel bearer credential; normally supplied by the Role.
    type: str
    required: true
  github_token:
    description: GitHub credential, required for Git source modes.
    type: str
  settings:
    description: Explicitly managed Vercel Project setting fields.
    type: dict
    default: {}
  deploy:
    description: Ensure an exact commit is active in production.
    type: bool
    default: false
  git_sha:
    description: Exact existing 40-character Git commit SHA when deploying.
    type: str
  deployment_timeout:
    description: Overall provider-operation and deployment wait budget, in seconds.
    type: int
    default: 900
  poll_interval:
    description: Seconds between deployment and promotion status reads.
    type: int
    default: 5
  retry_failed_deployment:
    description: Allow a new deployment after the newest matching deployment failed.
    type: bool
    default: false
  npx_executable:
    description: Path or command name for npx.
    type: str
    default: npx
  node_executable:
    description: Node executable whose directory should lead PATH for npm/npx shebangs.
    type: str
    default: node
  gh_executable:
    description: Path or command name for GitHub CLI.
    type: str
    default: gh
attributes:
  check_mode:
    support: partial
    details: Reports a conservative plan without provider inspection or npx downloads.
"""
EXAMPLES = r"""
- name: Create an empty Project in an explicit team
  madebyphunky.vercel.project:
    name: my-project
    scope_type: team
    scope_id: team_example
    vercel_token: "{{ VERCEL_TOKEN }}"
"""
RETURN = r"""
result:
  description: Sanitized public resource identities, state, URLs, and actions.
  returned: always
  type: dict
"""

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from urllib.parse import quote, urlencode

from ansible.module_utils.basic import AnsibleModule

SETTINGS = (
    "framework",
    "rootDirectory",
    "buildCommand",
    "installCommand",
    "outputDirectory",
)
FAILED = {"ERROR", "CANCELED", "BLOCKED", "DELETED"}
PENDING = {"QUEUED", "BUILDING", "INITIALIZING"}


class ProviderError(Exception):
    """A redacted provider or contract failure."""


class Project:
    def __init__(self, module):
        self.module = module
        self.p = module.params
        self.deadline = time.monotonic() + self.p["deployment_timeout"]
        self.changed = False
        self.result = {
            "project": None,
            "repository": None,
            "deployment": None,
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
        if p["deployment_timeout"] < 1 or p["poll_interval"] < 1:
            self.fail("Timeout and poll interval must be positive integers")
        if set(p["settings"]) - set(SETTINGS):
            self.fail(
                "Unsupported Project setting; use framework, rootDirectory, buildCommand, installCommand, outputDirectory"
            )
        if any(
            value is not None and not isinstance(value, str)
            for value in p["settings"].values()
        ):
            self.fail("Project settings must be strings or explicit null values")
        if p["source_mode"] != "none":
            for key in ("github_owner", "github_repository"):
                if (
                    not p[key]
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+", p[key])
                    or p[key] in (".", "..")
                ):
                    self.fail("Supply an explicit GitHub owner and repository name")
            if not (p["github_token"] or "").strip():
                self.fail("Supply GH_TOKEN for GitHub source modes")
        elif p["github_owner"] or p["github_repository"]:
            self.fail("GitHub identity requires an existing or ensure source mode")
        if p["deploy"] and (
            p["source_mode"] == "none"
            or not re.fullmatch(r"[0-9a-fA-F]{40}", p["git_sha"] or "")
        ):
            self.fail(
                "Deployment requires a GitHub source and exact 40-character existing commit SHA"
            )

    def redacted(self, text):
        for key in ("vercel_token", "github_token"):
            if self.p.get(key):
                text = text.replace(self.p[key], "<redacted>")
        return text

    def command(self, argv, data=None, environment=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.fail(
                "Provider-operation/deployment timeout exceeded; resources are retained"
            )
        env = os.environ.copy()
        env.update(
            {
                "CI": "1",
                "NO_COLOR": "1",
                "VERCEL_TELEMETRY_DISABLED": "1",
                "VERCEL_ORG_ID": "",
                "VERCEL_PROJECT_ID": "",
                "VERCEL_TEAM_ID": "",
                "GH_HOST": "github.com",
                "GH_REPO": "",
                "GH_CONFIG_DIR": self.directory,
                "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            }
        )
        node_directory = os.path.dirname(self.p["node_executable"])
        if node_directory:
            env["PATH"] = node_directory + os.pathsep + env.get("PATH", "")
        env.update(environment or {})
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

    def request(self, provider, path, method="GET", body=None, missing=False):
        if provider == "vercel":
            if self.p["scope_type"] == "team" and not path.startswith("/v2/user"):
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
            environment = {"VERCEL_TOKEN": self.p["vercel_token"]}
        else:
            argv = [
                self.p["gh_executable"],
                "api",
                path,
                "--method",
                method,
                "--include",
            ]
            if body is not None:
                argv.extend(["--input", "-"])
            environment = {"GH_TOKEN": self.p["github_token"]}
        rc, out, err = self.command(
            argv, json.dumps(body) if body is not None else None, environment
        )
        status_match = re.search(r"HTTP/\S+\s+(\d{3})", out)
        status = int(status_match.group(1)) if status_match else None
        # --include emits headers before the JSON body; headers have no opening object/array.
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
                "{} API {} {} failed{}: {}".format(
                    provider,
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

    def project_result(self, project):
        self.result["project"] = {
            "id": project.get("id"),
            "name": project.get("name"),
            "account_id": project.get("accountId"),
            "settings": {key: project.get(key) for key in SETTINGS},
        }

    def repository_result(self, repo):
        self.result["repository"] = {
            "id": repo.get("id"),
            "full_name": repo.get("full_name"),
            "url": repo.get("html_url"),
            "private": repo.get("private"),
        }

    def deployment_result(self, deployment, active=False):
        url = deployment.get("url")
        self.result["deployment"] = {
            "id": deployment.get("id") or deployment.get("uid"),
            "url": ("https://" + url) if url and not url.startswith("http") else url,
            "state": deployment.get("readyState") or deployment.get("state"),
            "sha": self.p["git_sha"].lower(),
            "active": active,
        }

    def deployment_error(self, deployment, message):
        details = [deployment.get("errorCode"), deployment.get("errorMessage")]
        error = deployment.get("error")
        if isinstance(error, dict):
            details.extend([error.get("code"), error.get("message")])
        elif isinstance(error, str):
            details.append(error)
        detail = "; ".join(str(value) for value in details if value)
        return message + ((": " + self.redacted(detail)) if detail else "")

    def inspect_project(self, missing=False):
        project = self.request(
            "vercel", "/v9/projects/" + quote(self.p["name"], safe=""), missing=missing
        )
        if project is not None:
            if project.get("name") != self.p["name"]:
                self.fail(
                    "Returned Project name does not match the explicit Project identity"
                )
            if project.get("accountId") != self.p["scope_id"]:
                self.fail(
                    "Returned Project owner does not match the explicit account/team ID"
                )
            self.project_result(project)
        return project

    def inspect_repository(self):
        identity = self.p["github_owner"] + "/" + self.p["github_repository"]
        repo = self.request("github", "/repos/" + identity, missing=True)
        if repo is not None:
            if (repo.get("full_name") or "").lower() != identity.lower():
                self.fail(
                    "Returned repository identity does not match the requested owner/name"
                )
            self.repository_result(repo)
        return repo

    def validate_link(self, project):
        link = (project or {}).get("link")
        if not link:
            return
        if self.p["source_mode"] == "none":
            self.fail(
                "Existing Project is Git-linked; none source mode will not silently unlink it"
            )
        actual = str(link.get("org", "")) + "/" + str(link.get("repo", ""))
        expected = self.p["github_owner"] + "/" + self.p["github_repository"]
        if link.get("type") != "github" or actual.lower() != expected.lower():
            self.fail(
                "Existing Project is linked to a different repository; refusing to relink"
            )

    def ensure_repository(self, repo):
        if repo is not None:
            return repo
        if self.p["source_mode"] == "existing":
            self.fail("Requested existing GitHub repository was not found")
        if self.p["deploy"]:
            self.fail(
                "Cannot deploy a nonexistent commit from a missing repository; create it and supply code first"
            )
        owner = self.request("github", "/users/" + self.p["github_owner"])
        if owner.get("type") == "Organization":
            endpoint = "/orgs/" + self.p["github_owner"] + "/repos"
        else:
            user = self.request("github", "/user")
            if (user.get("login") or "").lower() != self.p["github_owner"].lower():
                self.fail(
                    "Personal repository creation requires the token's authenticated owner"
                )
            endpoint = "/user/repos"
        self.action("create_repository")
        repo = self.request(
            "github",
            endpoint,
            "POST",
            {"name": self.p["github_repository"], "private": True, "auto_init": False},
        )
        expected = self.p["github_owner"] + "/" + self.p["github_repository"]
        if (repo.get("full_name") or "").lower() != expected.lower():
            self.fail(
                "Created repository identity does not match the requested owner/name"
            )
        self.repository_result(repo)
        return repo

    def pause(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.fail(
                "Deployment readiness/promotion timeout exceeded; resources are retained"
            )
        time.sleep(min(remaining, self.p["poll_interval"]))

    @staticmethod
    def state(deployment):
        return deployment.get("readyState") or deployment.get("state")

    @staticmethod
    def deployment_id(deployment):
        return deployment.get("id") or deployment.get("uid")

    def details(self, deployment):
        return self.request(
            "vercel", "/v13/deployments/" + self.deployment_id(deployment)
        )

    def deploy(self, project, repo):
        settings = {key: project.get(key) for key in SETTINGS}
        digest = hashlib.sha256(
            json.dumps(settings, sort_keys=True).encode()
        ).hexdigest()
        query = {
            "projectId": project["id"],
            "sha": self.p["git_sha"].lower(),
            "target": "production",
            "limit": 100,
        }
        match = None
        while True:
            page = self.request("vercel", "/v6/deployments?" + urlencode(query))
            for candidate in page.get("deployments", []):
                candidate = self.details(candidate)
                sha = (candidate.get("gitSource") or {}).get("sha") or (
                    candidate.get("meta") or {}
                ).get("githubCommitSha")
                if (sha or "").lower() != self.p["git_sha"].lower():
                    continue
                metadata = candidate.get("meta") or {}
                actual_settings = candidate.get("projectSettings")
                settings_match = metadata.get("madebyphunkySettingsHash") == digest
                if isinstance(actual_settings, dict):
                    settings_match = (
                        settings_match
                        or {key: actual_settings.get(key) for key in SETTINGS}
                        == settings
                    )
                if settings_match:
                    match = candidate
                    break
            if match or not (page.get("pagination") or {}).get("next"):
                break
            query["until"] = page["pagination"]["next"]
        if match and self.state(match) in FAILED:
            self.deployment_result(match)
            if not self.p["retry_failed_deployment"]:
                self.fail(
                    self.deployment_error(
                        match,
                        "Matching deployment failed; set vercel_retry_failed_deployment explicitly to retry",
                    )
                )
            match = None
        if match is None:
            self.action("create_deployment")
            match = self.request(
                "vercel",
                "/v13/deployments",
                "POST",
                {
                    "name": self.p["name"],
                    "project": project["id"],
                    "target": "production",
                    "gitSource": {
                        "type": "github",
                        "repoId": str(repo["id"]),
                        "sha": self.p["git_sha"].lower(),
                    },
                    "projectSettings": settings,
                    "skipAutoDetectionConfirmation": True,
                    "meta": {"madebyphunkySettingsHash": digest},
                },
            )
        while True:
            self.deployment_result(match)
            state = self.state(match)
            if state == "READY":
                break
            if state in FAILED:
                self.fail(
                    self.deployment_error(
                        match,
                        "Deployment ended in " + state + "; resources are retained",
                    )
                )
            if state not in PENDING:
                self.fail("Deployment returned an unsupported state: " + str(state))
            self.pause()
            match = self.details(match)
        project = self.inspect_project()
        if ((project.get("targets") or {}).get("production") or {}).get(
            "id"
        ) != self.deployment_id(match):
            self.action("promote_deployment")
            self.request(
                "vercel",
                "/v10/projects/"
                + project["id"]
                + "/promote/"
                + self.deployment_id(match),
                "POST",
            )
            while True:
                project = self.inspect_project()
                if ((project.get("targets") or {}).get("production") or {}).get(
                    "id"
                ) == self.deployment_id(match):
                    break
                self.pause()
        self.deployment_result(match, active=True)

    def converge(self):
        self.validate()
        if self.module.check_mode:
            self.changed = True
            self.result.update(
                inspection_limited=True,
                limitation="Provider state was not inspected: check mode never invokes npx, which could install/cache a package",
            )
            self.result["actions"] = ["inspect_and_ensure_project"]
            if self.p["source_mode"] != "none":
                self.result["actions"].append("inspect_and_ensure_repository_link")
            if self.p["deploy"]:
                self.result["actions"].append("inspect_and_ensure_production_commit")
            return
        identity_path = (
            "/v2/user"
            if self.p["scope_type"] == "personal"
            else "/v2/teams/" + self.p["scope_id"]
        )
        identity = self.request("vercel", identity_path)
        identity = identity.get("user", identity)
        if identity.get("id") != self.p["scope_id"]:
            self.fail(
                "Authenticated Vercel scope does not match the explicit account/team ID"
            )
        project = self.inspect_project(missing=True)
        self.validate_link(project)
        repo = None
        if self.p["source_mode"] != "none":
            repo = self.inspect_repository()
            if self.p["deploy"] and repo:
                commit = self.request(
                    "github",
                    "/repos/"
                    + self.p["github_owner"]
                    + "/"
                    + self.p["github_repository"]
                    + "/commits/"
                    + self.p["git_sha"],
                )
                if (commit.get("sha") or "").lower() != self.p["git_sha"].lower():
                    self.fail("GitHub did not resolve the requested exact commit")
            repo = self.ensure_repository(repo)
        if project is None:
            body = {"name": self.p["name"], **self.p["settings"]}
            if repo:
                body["gitRepository"] = {"type": "github", "repo": repo["full_name"]}
            self.action("create_project")
            project = self.request("vercel", "/v11/projects", "POST", body)
            self.project_result(project)
        elif repo and not project.get("link"):
            self.action("link_repository")
            self.request(
                "vercel",
                "/v9/projects/" + project["id"] + "/link",
                "POST",
                {"type": "github", "repo": repo["full_name"]},
            )
        if any(project.get(key) != value for key, value in self.p["settings"].items()):
            self.action("update_settings")
            project = self.request(
                "vercel", "/v9/projects/" + project["id"], "PATCH", self.p["settings"]
            )
            self.project_result(project)
        project = self.inspect_project()
        self.validate_link(project)
        if self.p["deploy"]:
            self.deploy(project, repo)


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
            "source_mode": {
                "type": "str",
                "choices": ["none", "existing", "ensure"],
                "default": "none",
            },
            "github_owner": {"type": "str"},
            "github_repository": {"type": "str"},
            "vercel_token": {"type": "str", "no_log": True, "required": True},
            "github_token": {"type": "str", "no_log": True},
            "settings": {"type": "dict", "default": {}},
            "deploy": {"type": "bool", "default": False},
            "git_sha": {"type": "str"},
            "deployment_timeout": {"type": "int", "default": 900},
            "poll_interval": {"type": "int", "default": 5},
            "retry_failed_deployment": {"type": "bool", "default": False},
            "npx_executable": {"type": "str", "default": "npx"},
            "gh_executable": {"type": "str", "default": "gh"},
            "node_executable": {"type": "str", "default": "node"},
        },
        supports_check_mode=True,
    )
    project = Project(module)
    try:
        with tempfile.TemporaryDirectory(prefix="vercel-project-") as directory:
            project.directory = directory
            project.converge()
    except (ProviderError, ValueError, KeyError) as error:
        module.fail_json(
            msg=project.redacted(str(error)),
            changed=project.changed,
            result=project.result,
        )
    module.exit_json(changed=project.changed, result=project.result)


if __name__ == "__main__":
    main()
