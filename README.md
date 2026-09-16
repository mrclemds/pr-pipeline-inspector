# PR Pipeline Inspector

`pr-pipeline-inspector` retrieves the most recent CI run for a pull request and prints commands to download its log and every associated artifact or report.

The tool consistently prints commands, not browser links. This keeps it usable in authenticated terminal sessions and makes downloads reproducible.

## Requirements

- Python 3.10 or newer. The inspector uses only the standard library; no `pip` packages or virtual environment are required.
- GitHub mode: GitHub CLI (`gh`) installed and authenticated with access to the repository and its checks.
- Azure mode: Azure CLI (`az`) installed, authenticated, and configured with the Azure DevOps extension.
- A GitHub repository in `OWNER/REPO` form for GitHub mode, or an Azure DevOps project name for Azure mode.

Check the local prerequisites with:

```sh
python3 --version
gh --version
gh auth status
az --version
az extension show --name azure-devops
```

## Authentication

The inspector delegates authentication to the vendor CLIs. It does not accept, handle, or store GitHub tokens, Azure credentials, or Azure DevOps PATs.

### GitHub

1. Install [GitHub CLI](https://cli.github.com/).
2. Run the interactive login flow:

  ```sh
  gh auth login
  ```

3. Confirm the active account and host:

  ```sh
  gh auth status
  ```

See the [`gh auth login` documentation](https://cli.github.com/manual/gh_auth_login) for browser, GitHub Enterprise, and non-interactive options. Use the [GitHub token settings page](https://github.com/settings/tokens) only when your organization's policy requires a token; grant the minimum repository and organization access needed to read the pull request and checks. Never pass a token on the command line or commit it to a file.

### Azure DevOps

1. Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).
2. Install the Azure DevOps extension:

  ```sh
  az extension add --name azure-devops
  ```

3. Sign in interactively with Microsoft Entra ID:

  ```sh
  az login
  ```

4. Configure defaults, or provide organization and project context through your existing Azure CLI configuration:

  ```sh
  az devops configure --defaults organization=https://dev.azure.com/ORGANIZATION project=PROJECT
  ```

5. Confirm the extension and current configuration:

  ```sh
  az extension show --name azure-devops
  az devops configure --list
  ```

See [Get started with the Azure DevOps CLI](https://learn.microsoft.com/en-us/azure/devops/cli/?view=azure-devops) and [Azure CLI authentication](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli) for installation and sign-in details. The Azure DevOps CLI extension supports Azure DevOps Services, not on-premises Azure DevOps Server.

If interactive sign-in is unavailable, follow [Sign in through an Azure DevOps PAT](https://learn.microsoft.com/en-us/azure/devops/cli/log-in-via-pat) and create one from the [Azure DevOps Personal access tokens settings page](https://app.vssps.visualstudio.com/app/register) with the narrowest available scope. Microsoft recommends [Microsoft Entra authentication over PATs](https://learn.microsoft.com/en-us/azure/devops/integrate/get-started/authentication/authentication-guidance); treat any PAT like a password, store it in an approved credential manager, and rotate or revoke it regularly.

Authentication errors can also be caused by organization policies, missing project permissions, expired credentials, or an incorrect Azure organization. The inspector cannot bypass those controls.

## Installation

There is no package registry release or installer. Run it directly from a checkout:

```sh
git clone <repository-url> pr-pipeline-inspector
cd pr-pipeline-inspector
./pr-pipeline-inspector --help
```

To make it available on `PATH`, keep the checkout in a stable location and create a symlink. Keep the launcher beside `pr_pipeline_inspector.py`:

```sh
mkdir -p "$HOME/.local/bin"
ln -sfn "$PWD/pr-pipeline-inspector" "$HOME/.local/bin/pr-pipeline-inspector"
export PATH="$HOME/.local/bin:$PATH"
pr-pipeline-inspector --help
```

Add the `PATH` export to your shell startup file for future sessions. Updating the checkout updates the command; remove the symlink to uninstall it.

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

GitHub uses the repository supplied by `--repo`. Azure uses the project supplied by `--project`; Azure organization context must already be configured for `az devops`.

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

If the Azure CLI executable is wrapped or installed under another name, pass it with `--azure-cli`. The value must be on `PATH` or an absolute path.

## Verification

```sh
python3 -m unittest discover -s tests -v
```

Run this from the repository root. The tests mock external CLI calls and do not require GitHub or Azure credentials.

## Troubleshooting

- `Required CLI is not installed`: install the CLI named in the error and make sure it is on `PATH`.
- GitHub reports no run: check the PR number, `OWNER/REPO`, and `gh auth status`; the tool selects a run for the PR head commit.
- Azure reports no build: check the project, PR number, Azure authentication, and the pull-request merge ref.
- Commands are printed but not executed: this is intentional. Run the selected command in an authenticated shell to download logs or artifacts.
