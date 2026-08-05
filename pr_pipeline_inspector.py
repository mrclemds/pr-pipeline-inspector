#!/usr/bin/env python3
"""Summarize the latest CI run for a GitHub or Azure DevOps pull request."""

from __future__ import annotations

import argparse
import json
import logging
from urllib.parse import urlparse, parse_qs
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence


LOG = logging.getLogger("pr-pipeline-inspector")


@dataclass
class Run:
    build_id: str
    build_number: str | None
    attempt: str
    status: str
    conclusion: str
    name: str
    log_command: str
    stages: list[tuple[str, str, str, str | None]]
    artifacts: list[tuple[str, str]]


class CommandError(RuntimeError):
    pass


def run_json(command: Sequence[str]) -> Any:
    LOG.debug("Executing: %s", " ".join(command))
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise CommandError(f"Required CLI is not installed: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip()
        raise CommandError(f"Command failed ({' '.join(command)}): {detail}") from error
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CommandError(f"Command did not return JSON: {' '.join(command)}") from error


def response_values(payload: Any) -> list[dict[str, Any]]:
    return payload.get("value", payload) if isinstance(payload, dict) else payload


def discover_azure_projects(pr_number: int, repository: str) -> list[dict[str, Any]]:
    checks = run_json(["gh", "pr", "view", str(pr_number), "--repo", repository, "--json", "statusCheckRollup"])
    projects: dict[tuple[str, str], dict[str, Any]] = {}
    for check in checks.get("statusCheckRollup", []):
        url = check.get("detailsUrl") or check.get("targetUrl")
        if not url:
            continue
        parsed = urlparse(url)
        path = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.endswith(".visualstudio.com") and path:
            organization, project = parsed.netloc.split(".", 1)[0], path[0]
        elif parsed.netloc == "dev.azure.com" and len(path) >= 2:
            organization, project = path[0], path[1]
        else:
            continue
        candidate = projects.setdefault((organization, project), {"organization": organization, "project": project, "checks": []})
        candidate["checks"].append({
            "name": check.get("name") or check.get("context") or "unnamed",
            "result": check.get("conclusion") or check.get("state") or "unknown",
            "build_id": parse_qs(parsed.query).get("buildId", [None])[0],
            "url": url,
        })
    return list(projects.values())


def print_azure_projects(pr_number: int, repository: str, projects: list[dict[str, Any]]) -> None:
    if not projects:
        print("No Azure DevOps projects were found in GitHub PR check URLs.")
        return
    print(f"PR: {pr_number}\nRepository: {repository}\nAzure DevOps projects discovered from GitHub checks:")
    for candidate in projects:
        print(f"\nOrganization: {candidate['organization']}\nProject: {candidate['project']}")
        print("Checks:")
        for check in candidate["checks"]:
            build = f", build {check['build_id']}" if check["build_id"] else ""
            print(f"  {check['name']}: {check['result']}{build}\n    {check['url']}")
        print("Inspection command:")
        print(f"  pr-pipeline-inspector {pr_number} --backend azure --project {candidate['project']} --azure-cli azure-devops-cli --verbose")


def github_run(pr_number: int, repository: str) -> Run:
    pr = run_json(["gh", "pr", "view", str(pr_number), "--repo", repository, "--json", "headRefOid"])
    runs = run_json([
        "gh", "run", "list", "--repo", repository, "--commit", pr["headRefOid"], "--limit", "1",
        "--json", "databaseId,workflowName,status,conclusion,number",
    ])
    if not runs:
        raise CommandError("No GitHub Actions runs found for this pull request head commit.")
    latest = runs[0]
    build_id = str(latest["databaseId"])
    details = run_json(["gh", "run", "view", build_id, "--repo", repository, "--json", "jobs"])
    metadata = run_json(["gh", "api", f"repos/{repository}/actions/runs/{build_id}"])
    artifacts = run_json(["gh", "api", f"repos/{repository}/actions/runs/{build_id}/artifacts"])
    stages = [
        (job.get("name", "unnamed"), job.get("status", "unknown"), job.get("conclusion") or "pending", None)
        for job in details.get("jobs", [])
    ]
    report_artifacts = [
        (artifact["name"], f"gh run download {build_id} --repo {repository} --name {artifact['name']}")
        for artifact in artifacts.get("artifacts", [])
    ]
    return Run(
        build_id=build_id,
        build_number=None,
        attempt=str(metadata.get("run_attempt", latest.get("number", 1))),
        status=latest.get("status", "unknown"),
        conclusion=latest.get("conclusion") or "pending",
        name=latest.get("workflowName", "GitHub Actions"),
        log_command=f"gh run view {build_id} --repo {repository} --log > run-{build_id}.log",
        stages=stages,
        artifacts=report_artifacts,
    )


def azure_run(pr_number: int, project: str, azure_cli: str) -> Run:
    builds = response_values(run_json([
        azure_cli, "devops", "invoke", "--area", "build", "--resource", "builds",
        "--route-parameters", f"project={project}",
        "--query-parameters", f"branchName=refs/pull/{pr_number}/merge&queryOrder=finishTimeDescending&$top=1",
        "--api-version", "7.1",
    ]))
    if not builds:
        raise CommandError("No Azure Pipeline builds found for refs/pull/%s/merge." % pr_number)
    latest = builds[0]
    build_id = str(latest["id"])
    timeline = run_json([
        azure_cli, "devops", "invoke", "--area", "build", "--resource", "timeline",
        "--route-parameters", f"project={project}", f"buildId={build_id}", "--api-version", "7.1",
    ])
    artifacts = response_values(run_json([
        azure_cli, "devops", "invoke", "--area", "build", "--resource", "artifacts",
        "--route-parameters", f"project={project}", f"buildId={build_id}", "--api-version", "7.1",
    ]))
    logs = response_values(run_json([
        azure_cli, "devops", "invoke", "--area", "build", "--resource", "logs",
        "--route-parameters", f"project={project}", f"buildId={build_id}", "--api-version", "7.1",
    ]))
    if not logs:
        raise CommandError(f"Azure build {build_id} has no logs.")
    latest_log_id = str(logs[-1]["id"])
    stages = [
        (
            record.get("name", "unnamed"), record.get("state", "unknown"), record.get("result") or "pending",
            str(record["attempt"]) if record.get("attempt") is not None else None,
        )
        for record in timeline.get("records", []) if record.get("type") == "Stage"
    ]
    report_artifacts = [
        (
            artifact["name"],
            f"{azure_cli} devops invoke --area build --resource artifacts --route-parameters "
            f"project={project} buildId={build_id} artifactName={artifact['name']} --api-version 7.1",
        )
        for artifact in artifacts
    ]
    return Run(
        build_id=build_id,
        build_number=str(latest.get("buildNumber", "unavailable")),
        attempt="unavailable",
        status=latest.get("status", "unknown"),
        conclusion=latest.get("result") or "pending",
        name=latest.get("definition", {}).get("name", "Azure Pipeline"),
        log_command=f"{azure_cli} devops invoke --area build --resource logs --route-parameters project={project} "
        f"buildId={build_id} logId={latest_log_id} --api-version 7.1 > build-{build_id}-log-{latest_log_id}.log",
        stages=stages,
        artifacts=report_artifacts,
    )


def print_run(pr_number: int, backend: str, run: Run) -> None:
    LOG.info("resolved_run backend=%s pr_number=%s build_id=%s attempt=%s", backend, pr_number, run.build_id, run.attempt)
    print(f"PR: {pr_number}\nBackend: {backend}\nPipeline: {run.name}")
    build_details = f"Build ID: {run.build_id}"
    if run.build_number:
        build_details += f"\nBuild number: {run.build_number}"
    print(f"{build_details}\nAttempt: {run.attempt}\nStatus: {run.status}\nResult: {run.conclusion}")
    print(f"\nLog command:\n  {run.log_command}")
    print("\nStages:")
    if run.stages:
        for name, status, result, attempt in run.stages:
            attempt_detail = f", attempt {attempt}" if attempt is not None else ""
            print(f"  {name}: {status} ({result}{attempt_detail})")
    else:
        print("  No stages reported.")
    print("\nAssociated artifacts and reports:")
    if run.artifacts:
        for name, command in run.artifacts:
            print(f"  {name}:\n    {command}")
    else:
        print("  No artifacts reported.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--backend", choices=("github", "azure"))
    parser.add_argument("--repo", help="GitHub repository in OWNER/REPO form")
    parser.add_argument("--discover-azure-project", action="store_true", help="Discover Azure DevOps projects from GitHub PR checks")
    parser.add_argument("--project", help="Azure DevOps project")
    parser.add_argument("--azure-cli", default="az", help="Azure CLI command")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.discover_azure_project:
            if not args.repo:
                parser.error("--repo is required with --discover-azure-project")
            projects = discover_azure_projects(args.pr_number, args.repo)
            print_azure_projects(args.pr_number, args.repo, projects)
            return 0
        if not args.backend:
            parser.error("--backend is required unless --discover-azure-project is used")
        LOG.info("investigating backend=%s pr_number=%s build_id=unknown attempt=unknown", args.backend, args.pr_number)
        if args.backend == "github":
            if not args.repo:
                parser.error("--repo is required with --backend github")
            run = github_run(args.pr_number, args.repo)
        else:
            if not args.project:
                parser.error("--project is required with --backend azure")
            if not shutil.which(args.azure_cli):
                raise CommandError(f"Azure DevOps CLI wrapper is unavailable: {args.azure_cli}")
            run = azure_run(args.pr_number, args.project, args.azure_cli)
        print_run(args.pr_number, args.backend, run)
        return 0
    except CommandError as error:
        LOG.error("pr_number=%s build_id=unknown attempt=unknown: %s", args.pr_number, error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
