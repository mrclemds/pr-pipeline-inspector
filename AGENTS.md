# PR Pipeline Inspector Instructions

- Keep the CLI dependency-free and compatible with the system Python 3.
- Output commands, never browser links, for logs and downloaded artifacts.
- Every backend must report the PR number and build ID. Report attempts only when the backend supplies one; never infer an attempt from Azure build number.
- Discover artifacts dynamically; do not add fixed report-name allowlists for Allure, Aqua, or scan reports.
- Use `gh` for GitHub and `az devops` for Azure DevOps. Do not handle credentials in this repository.
- Use `--discover-azure-project --repo OWNER/REPOSITORY` to identify Azure project identifiers from GitHub PR check URLs when the project is unknown.
- Run `python3 -m unittest discover -s tests -v` after code changes.
