# Immutable release test

WorkflowTester now tests the proposed fix for Snowflake's release workflow.

1. Release Please maintains a version/changelog PR.
2. After the PR is merged, it creates a **draft** GitHub release (`draft: true`).
3. The action explicitly dispatches `release.yml` with the release tag name and full commit SHA. Draft creation does not create a Git tag, so a tag-push trigger would not work.
4. The build job validates the inputs, checks out that SHA, checks its package version matches the intended tag, and packs the library with read-only permissions.
5. After `nuget-release` environment approval, the write-enabled publishing job verifies the release is still a draft, then attests and pushes the package to NuGet.org. Draft visibility requires push access, so draft lookup must not run in the read-only build job.
6. It uploads the `.nupkg` to the draft, then publishes the GitHub release. Publication creates the tag and freezes the attached asset under release immutability.

## Required setup

- Keep release immutability enabled.
- Configure the repository Actions secret `RELEASE_PLEASE_TOKEN` for Release Please. Scope it to this repository with Contents and Pull requests write access. The repository setting allowing the built-in Actions token to create/approve PRs can remain disabled.
- Release Please uses the separate token to manage release PRs and draft releases, matching Snowflake. The built-in GitHub token only has Contents read and Actions write for explicitly dispatching `release.yml`; it is not granted Pull requests write.
- Keep `NUGET_USER`, the `nuget-release` environment approval gate, and the NuGet Trusted Publishing policy for `release.yml`. The publishing workflow runs on `main` via dispatch, so any environment branch restrictions must allow `main`.
- The policy must allow the existing workflow/environment combination to authenticate when dispatched from `main`.

## Adaptations for the test repository

- Package: `WorkflowTester.Lib`; project: `src/WorkflowTester.Lib`.
- Tags use `dotnet/v*` instead of `csharp/v*`.
- `release.yml` retains its filename to match the existing NuGet policy.
- Stable versions come from the project file and Release Please manifest.
- MinVer remains enabled only for the separate manual preview workflow.

## Baselines

- `dotnet/v0.0.3`: original workflow succeeded with a mutable release.
- `dotnet/v0.0.4`: original workflow succeeded with an immutable release and attached package using `softprops/action-gh-release`.
- Commit `5dd9787`: mirrored Snowflake's publish-before-upload sequence. Its Release Please run failed because `RELEASE_PLEASE_TOKEN` was absent, so that sequence was not exercised end to end.

## Verification and recovery

Merge the generated release PR, approve the dispatched publishing run, then verify that the public release is immutable and contains the correctly versioned `.nupkg`.

For a draft left behind after dispatch failure, run `release.yml` manually with its intended tag name and full release commit SHA. Do not publish the draft manually before the package is attached.

If publishing fails after NuGet upload, the package may already exist on NuGet.org. Do not blindly rerun the complete publishing job: complete the remaining draft upload/publication steps using the original build artifact.
