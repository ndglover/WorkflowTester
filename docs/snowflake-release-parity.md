# Immutable release test

WorkflowTester trials a single release workflow that stages a downloadable candidate before publishing approval.

1. Release Please maintains a version/changelog PR.
2. After the PR is merged, it creates a **draft** GitHub release (`draft: true`).
3. The action explicitly dispatches `release.yml` with the release tag name and full commit SHA. Draft creation does not create a Git tag, so a tag-push trigger would not work.
4. The build job validates the inputs, checks out that SHA, checks its package version matches the intended tag, and packs the library with read-only permissions.
5. The separate write-enabled candidate job verifies the draft and source commit, generates provenance, and attaches the package and attestation bundle to the draft. It downloads and verifies the assets and writes the draft link and package digest to the run summary. Maintainers can now download and test the candidate.
6. After `nuget-release` environment approval, the publishing job downloads that same attached candidate, checks its recorded SHA-256 and attestation/source, and pushes to NuGet.org. A final job publishes the draft and freezes the assets under release immutability.

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

The release workflow uses separate build, candidate preparation, NuGet publication, and GitHub publication jobs. Use **Re-run failed jobs** after a partial failure: successful jobs are not repeated, and later jobs download the original saved package. A full rerun builds another package; after NuGet publication, prefer resuming the original run. NuGet versions cannot be replaced. If an upload was accepted but its job failed, inspect the existing package or draft asset before recovering manually.


## Normal pipeline trial

The test branch moves attestation and draft attachment before the publishing approval gate. The Snowflake workflow is unchanged until this trial is reviewed. Temporary failure injection and the one-off retry/source verification workflows have been removed. Published test releases retain the earlier verification history.


## Candidate preparation without publication

Dispatch release.yml with publish=false to build, attest, and attach a candidate without starting either publication job. The source SHA must match the draft target and package version. A candidate may be deliberately replaced while the release is a draft and the NuGet version has not been published; test and approve the replacement again. Each run records its own digest, so changing an attached asset after staging causes that run's publication check to fail.


## Avoiding repeated release PRs while approval is pending

Prepare Release first processes merged release PRs without opening another PR. It then checks whether the current manifest version has a draft release. If so, it waits for that release to be published rather than asking Release Please to calculate another version against the old published baseline. A newly created draft is still dispatched to the Release workflow.

The current-version check deliberately ignores the separate 0.0.900 branch-test fixture. Once the current release is published, the next relevant push can maintain a new release PR normally. Merging a release PR prepares its candidate; publishing approval is the next action, rather than merging another version PR.