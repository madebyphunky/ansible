#!/usr/bin/env python3
"""Isolated CLI boundary double; models provider resources, never the Ansible Role."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

path = Path(os.environ["VERCEL_CONTRACT_STATE"])
data = json.loads(path.read_text())
args = sys.argv[1:]
provider = "vercel" if Path(sys.argv[0]).name == "npx" else "github"
endpoint = args[args.index("api") + 1]
method = args[args.index("--method") + 1]
body = json.load(sys.stdin) if "--input" in args else None
query = parse_qs(urlsplit(endpoint).query)
route = urlsplit(endpoint).path
expected = os.environ.get(
    "VERCEL_CONTRACT_EXPECT_" + provider.upper(), "dummy-" + provider
)
token = os.environ.get("VERCEL_TOKEN" if provider == "vercel" else "GH_TOKEN")
data.setdefault("calls", []).append(
    {
        "provider": provider,
        "path": route,
        "query": query,
        "method": method,
        "body": body,
        "explicit_scope": query.get("teamId"),
    }
)


def reply(value, status=200):
    path.write_text(json.dumps(data))
    print("HTTP/2.0 " + str(status))
    print("Content-Type: application/json\n")
    print(json.dumps(value))
    raise SystemExit(0 if status < 400 else 1)


if token != expected:
    reply({"error": {"message": "Credential rejected: " + str(token)}}, 401)

if provider == "github":
    if route == "/user":
        reply({"login": data.get("user", "tester")})
    if route.startswith("/users/"):
        owner = route.split("/")[-1]
        reply({"login": owner, "type": data.get("owner_type", "User")})
    if method == "POST":
        owner = (
            route.split("/")[2]
            if route.startswith("/orgs/")
            else data.get("user", "tester")
        )
        repo = {
            "id": 101,
            "full_name": owner + "/" + body["name"],
            "private": body["private"],
            "html_url": "https://github.com/" + owner + "/" + body["name"],
        }
        data["repository"] = repo
        reply(repo, 201)
    if "/commits/" in route:
        sha = route.split("/")[-1]
        if sha not in data.get("commits", []):
            reply({"message": "Commit missing"}, 422)
        reply({"sha": sha})
    if route.startswith("/repos/"):
        repo = data.get("repository")
        reply(repo if repo else {"message": "Not Found"}, 200 if repo else 404)

if route == "/v2/user":
    reply({"user": {"id": data.get("personal_id", "user_test")}})
if route.startswith("/v2/teams/"):
    reply({"id": data.get("team_id", "team_test")})
if route == "/v11/projects" and method == "POST":
    if body.get("gitRepository") and data.get("app_access_denied"):
        reply(
            {
                "error": {
                    "message": "Install Vercel GitHub App and grant repository access"
                }
            },
            403,
        )
    project = {
        "id": "prj_test",
        "name": body["name"],
        "accountId": data.get("account_id", "team_test"),
        "targets": {},
    }
    project.update(
        {
            key: value
            for key, value in body.items()
            if key not in ("name", "gitRepository")
        }
    )
    if body.get("gitRepository"):
        owner, repository = body["gitRepository"]["repo"].split("/")
        project["link"] = {"type": "github", "org": owner, "repo": repository}
    data["project"] = project
    reply(project, 201)
if "/env" in route and (
    route.startswith("/v9/projects/") or route.startswith("/v10/projects/")
):
    project = data.get("project")
    if project is None:
        reply({"error": {"message": "Not Found"}}, 404)
    envs = data.setdefault("envs", [])
    if method == "GET" and route.endswith("/env"):
        visible = []
        for item in envs:
            row = dict(item)
            if row.get("type") == "sensitive":
                row["value"] = None
            visible.append(row)
        reply({"envs": visible})
    if method == "POST" and route.endswith("/env"):
        created = dict(body)
        created.setdefault("id", "env_" + str(len(envs) + 1))
        envs.append(dict(created))
        response = dict(created)
        if response.get("type") == "sensitive":
            response["value"] = None
        reply(response, 201)
    if method == "PATCH" and "/env/" in route:
        env_id = route.rstrip("/").split("/")[-1]
        existing = next((item for item in envs if item.get("id") == env_id), None)
        if existing is None:
            reply({"error": {"message": "Env Not Found"}}, 404)
        existing.update(body)
        if existing.get("type") == "sensitive":
            existing["value"] = body.get("value", existing.get("value"))
        reply(existing)
    reply({"error": {"message": "Unhandled env route " + route}}, 500)
if route.startswith("/v9/projects/"):
    project = data.get("project")
    if project is None:
        reply({"error": {"message": "Not Found"}}, 404)
    if route.endswith("/link"):
        if data.get("app_access_denied"):
            reply(
                {
                    "error": {
                        "message": "Install Vercel GitHub App and grant repository access"
                    }
                },
                403,
            )
        owner, repository = body["repo"].split("/")
        project["link"] = {"type": "github", "org": owner, "repo": repository}
    elif method == "PATCH":
        project.update(body)
    reply(project)
if route == "/v6/deployments":
    deployments = [
        deployment
        for deployment in data.get("deployments", [])
        if deployment.get("gitSource", {}).get("sha") == query["sha"][0]
    ]
    reply({"deployments": deployments[::-1], "pagination": {"next": None}})
if route == "/v13/deployments" and method == "POST":
    deployment = {
        "id": "dpl_" + str(len(data.get("deployments", [])) + 1),
        "url": "test-deployment.vercel.app",
        "readyState": data.get("new_deployment_state", "READY"),
        "gitSource": body["gitSource"],
        "projectSettings": body["projectSettings"],
        "meta": body["meta"],
        "errorMessage": data.get("deployment_error_message"),
    }
    data.setdefault("deployments", []).append(deployment)
    if deployment["readyState"] == "READY":
        data["project"]["targets"] = {"production": {"id": deployment["id"]}}
    reply(deployment, 201)
if route.startswith("/v13/deployments/"):
    deployment = next(
        item for item in data["deployments"] if item["id"] == route.split("/")[-1]
    )
    if deployment["readyState"] == "BUILDING" and data.get("finish_pending", False):
        deployment["readyState"] = "READY"
        data["project"]["targets"] = {"production": {"id": deployment["id"]}}
    reply(deployment)
if route.startswith("/v10/projects/") and "/promote/" in route:
    deployment_id = route.split("/")[-1]
    data["project"]["targets"] = {"production": {"id": deployment_id}}
    reply({"id": deployment_id})
reply({"error": {"message": "Unhandled fixture request " + route}}, 500)
