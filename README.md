# PR Pipeline Inspector

`pr-pipeline-inspector` retrieves the most recent CI run for a pull request and prints commands to download its log and every associated artifact or report.

The tool consistently prints commands, not browser links. This keeps it usable in authenticated terminal sessions and makes downloads reproducible.

## Usage

```sh
./pr-pipeline-inspector 42 --backend github --repo owner/repository
./pr-pipeline-inspector 42 --backend azure --project ProjectName
```

Optional arguments:

```text
--azure-cli PATH_OR_COMMAND  Azure CLI command; defaults to az
--verbose                    Print every command executed by the inspector
```

The tool writes progress logs to stderr. Every resolved run logs the PR number, build ID, and attempt. The output on stdout is a stable investigation report containing:

- The selected pipeline, build ID, build number when supplied by Azure, attempt when supplied by the backend, state, and result.
- A single copyable command to download the latest log.
- A stage/job recap with state and result.
- A command for each dynamically discovered artifact. This includes Allure, Aqua, security scans, and any other published artifact without relying on fixed names.

## Backends

GitHub resolves the PR head commit using `gh`, selects its newest GitHub Actions run, and generates `gh run` download commands.

Azure DevOps queries the merge ref `refs/pull/PR_NUMBER/merge` through `az devops invoke`, then retrieves the build timeline, logs, and artifacts through the same interface. Azure requires the Azure CLI and Azure DevOps extension.

The CLI deliberately outputs commands rather than browser links. Commands work in authenticated terminal sessions and preserve an auditable, reproducible investigation path.

## Azure Project Discovery

When the Azure DevOps project is unknown, inspect GitHub PR check metadata first:

```sh
./pr-pipeline-inspector 42 --repo owner/repository --discover-azure-project --verbose
```

The command discovers Azure DevOps URLs from external checks and reports each organization, project identifier, build ID, check result, and source URL. Use the discovered project identifier with the Azure backend.

## Examples

```sh
# Show the latest GitHub Actions result and commands for PR 42.
./pr-pipeline-inspector 42 --backend github --repo owner/repository

# Use a custom Azure DevOps wrapper.
./pr-pipeline-inspector 42 --backend azure --project ProjectName \
  --azure-cli /path/to/az
```

After deployment, invoke the managed launcher from any directory:

```sh
pr-pipeline-inspector 42 --backend github --repo owner/repository
```

The installed command is self-contained, so it remains usable without this repository.

## Verification

```sh
python3 -m unittest discover -s tests -v
```
