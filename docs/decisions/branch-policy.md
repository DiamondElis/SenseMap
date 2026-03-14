# Branch policy

## Protected branch: `main`

- **`main`** is the default and only long-lived branch. It must be **protected** in GitHub:
  - **Settings → Branches → Branch protection rules** for `main`
  - Require a pull request before merging (at least 1 approval optional; configurable)
  - Require status checks to pass: **`lint`** and **`test`** (must be selected in the rule)
  - Do not allow force pushes or deletion of the branch
  - Optionally: require linear history, restrict who can push

Branch protection is configured in the GitHub repo settings, not in this repository.

## Short-lived feature branches

- All changes go through **short-lived branches** off `main`.
- **Branch naming** (aligned with [Conventional Commits](https://www.conventionalcommits.org/) and `.commitlintrc.json`):
  - `feature/<scope-or-description>` — new features (e.g. `feature/ingestion-pdf`)
  - `fix/<description>` — bug fixes (e.g. `fix/neo4j-timeout`)
  - `docs/<description>` — documentation only
  - `chore/<description>` — tooling, config, deps
- Create a branch, make focused commits, open a PR, merge to `main`, then **delete the branch** after merge. Keep branches short-lived (days, not weeks).

## PR-required checks

- Merging into `main` is **only** via **pull request** (enforced by branch protection).
- The following status checks must pass before merge (enable in branch protection):
  - **`lint`** — Ruff (and any other linters you add)
  - **`test`** — Pytest (and any other test jobs you add)
  - **`commitlint`** — Conventional commit message validation on the PR’s commits

No direct pushes to `main`; all integration happens through PRs.
