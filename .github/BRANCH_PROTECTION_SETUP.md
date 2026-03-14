# Branch protection setup (one-time)

Configure in **GitHub → Repository → Settings → Branches → Add branch protection rule**.

## Branch name pattern
`main`

## Recommended settings

| Setting | Value |
|--------|--------|
| Require a pull request before merging | Yes (at least 1) |
| Require status checks to pass before merging | Yes |
| **Status checks that are required** | **`lint`**, **`test`**, **`commitlint`** |
| Require branches to be up to date before merging | Optional |
| Do not allow bypassing the above settings | Recommended |
| Restrict who can push to matching branches | Optional |
| Allow force pushes | No |
| Allow deletion | No |

The status check names **`lint`**, **`test`**, and **`commitlint`** come from the workflow job names in `.github/workflows/ci.yml` and `.github/workflows/commitlint.yml`. They appear in the list after at least one run on a PR.
