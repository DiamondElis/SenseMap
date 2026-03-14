# Semantic version tags for deployable services

## Policy

Deployable artifacts (API, web app, workers, or any service we release) use **semantic version tags**:

- Format: **`v<major>.<minor>.<patch>`** (e.g. `v1.2.3`)
- **Major**: breaking changes (API contract, config, or behaviour that requires migration)
- **Minor**: new features or improvements, backward-compatible
- **Patch**: bug fixes and safe changes, backward-compatible

Tags are created on **`main`** after a PR is merged when the change is deemed release-worthy. Tags can be service-specific (e.g. `api/v1.0.0`, `web/v1.0.0`) or monorepo-wide (`v1.0.0`) depending on how you deploy.

## Tag format (monorepo)

- Use a single sequence for the repo: `v1.0.0`, `v1.1.0`, `v2.0.0`, …
- Tag from the commit on `main` that you intend to deploy.

## Tag format (per-service, optional)

If you version services separately:

- `api/v1.0.0`, `web/v1.0.0`, `worker/v1.0.0`
- Create the tag when that service is ready to be deployed.

## Creating a tag

```bash
# After merging to main and deciding to release
git checkout main
git pull origin main
git tag -a v1.2.3 -m "Release v1.2.3: short description"
git push origin v1.2.3
```

## CI/CD

- Use tag push events in GitHub Actions (or your CI) to trigger builds and deployments.
- Validate tag format (e.g. `^v\d+\.\d+\.\d+(-.*)?$`) in a workflow if you want to reject invalid tags.
