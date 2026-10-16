# Snowflake release workflow parity

The stable release test mirrors adbc-drivers/snowflake's release sequence:

1. Release Please maintains a version/changelog PR.
2. Merging that PR publishes the GitHub release and creates a `dotnet/v*` tag.
3. `release.yml` packs the library and awaits `nuget-release` approval.
4. It attests the package, authenticates through NuGet Trusted Publishing, and pushes to NuGet.org.
5. It runs `gh release upload` against the release that Release Please already published.

With release immutability enabled, step 5 is expected to fail with HTTP 422.
This deliberately reproduces the current production behavior before testing a fix.

## Required setup

- Keep release immutability enabled.
- Configure a repository Actions secret named `RELEASE_PLEASE_TOKEN`, with permission to manage release PRs, tags, and releases in this repository. A separate token is required so the tag creation triggers the publishing workflow, as in Snowflake.
- Permit GitHub Actions to create pull requests where required by repository settings.
- Keep the existing `NUGET_USER` variable, `nuget-release` environment, and NuGet Trusted Publishing policy for `release.yml`.
- Keep the existing environment approval gate.

## Adaptations for the test repository

- Package: `WorkflowTester.Lib`; project: `src/WorkflowTester.Lib`.
- Tags use `dotnet/v*` instead of `csharp/v*`.
- The publishing workflow remains named `release.yml` because NuGet's policy binds to that filename.
- Stable versions come from the project file and Release Please manifest, seeded at the last test release, `0.0.4`.
- MinVer is only enabled for the existing manual preview workflow, which supplies `MinVerVersionOverride`.
- Checkout keeps Snowflake's submodule option even though this test repository has no submodules.

## Baselines

- `dotnet/v0.0.3`: original workflow succeeded with a mutable release.
- `dotnet/v0.0.4`: original workflow succeeded with an immutable release and attached package. That workflow used `softprops/action-gh-release`, so it did not reproduce Snowflake's separate release creation and upload.

Do not rerun a release's publishing job blindly after an upload failure: NuGet publication occurs before the GitHub upload and may already have succeeded.
