# Releasing `skylightctl` to PyPI

The CLI is published as the `skylightctl` Python package. Once published, users
can install it with:

```bash
uv tool install skylightctl
```

## One-Time PyPI Setup

Create a PyPI account with 2FA enabled, then add a pending trusted publisher for
the first release:

- PyPI project name: `skylightctl`
- Owner: `JamesHWade`
- Repository: `SkylightAPI`
- Workflow name: `publish.yml`
- Environment name: `pypi`

The matching workflow is `.github/workflows/publish.yml`. It uses PyPI Trusted
Publishing, so no long-lived PyPI API token is stored in GitHub.

## Release Checklist

1. Update the version in `cli/pyproject.toml`.
2. Update `cli/uv.lock`:

   ```bash
   cd cli
   uv lock
   ```

3. Validate locally:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run ty check
   uv build
   ```

4. Tag and push from the repository root:

   ```bash
   git tag skylightctl-v0.1.0
   git push origin skylightctl-v0.1.0
   ```

5. Confirm the `Publish CLI to PyPI` workflow succeeds.

PyPI release files are immutable. If a release build is wrong, bump the version
and publish a new release.
