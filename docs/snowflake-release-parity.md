# Release PR previews and final publication

WorkflowTester uses one workflow, `.github/workflows/release.yml`, with standard Release Please actions and shell steps. It does not require the custom candidate-version `.cjs` helper proposed in PR #16.

## Before the release PR is merged

Each relevant code PR merged into main updates the single Release Please PR, including its version and changelog. Build the preview from that release PR's exact head commit, so its version files and proposed code match. For example, merging code PR #15 can produce `1.0.0-preview.15`. The suffix identifies the triggering code PR, not the release PR. Rerunning the same source retains that package version; each workflow attempt has a separate artifact name.

Previews are GitHub Actions artifacts, never NuGet.org publications or GitHub release assets. They contain the nupkg, symbols, and `preview-source.json` recording the release PR, triggering code PR and exact source SHA. The release PR description starts with a prominent Download preview package link, version, retention period, triggering code PR and exact source SHA. Each successful preview replaces that section while preserving Release Please's generated notes. Stale previews cannot change a description after the PR head advances. The commit status and workflow summary also link to the download.

Repository Actions variable `PREVIEW_RETENTION_DAYS` configures preview retention. The default is 28 days when unset. For this public repository the value must be a whole number from 1 to 90, within repository/organization retention limits. Retention starts at upload; changing the variable affects subsequent uploads. There is no automatic custom cleanup job.

## After the release PR is merged

Release Please creates the draft final release and selects the merged release commit. Build its final version separately, without a preview suffix. Attach that nupkg and signed provenance to the draft before waiting for the `nuget-release` approval. After approval, download and verify that same final asset, push it to NuGet, and publish the GitHub release. Published release assets are permanent under release immutability; preview artifact retention does not apply to them.

New code merged while final publication is waiting cannot change the selected final source, version or approval. After successful final publication, the workflow dispatches a preparation-only main run to maintain the next release PR, including code accumulated during that wait. That follow-up run does not dispatch another run unless it subsequently publishes a final release. This guard prevents duplicate release PRs against an unpublished draft. Drafts managed by this flow carry `<!-- release-pr-candidate -->` in their notes. Older trial drafts without that marker are not treated as this flow's pending final release.

The publication marker `<!-- publication-started -->` preserves the existing partial-publication recovery rule: resume the original run after publication starts. Do not cancel the whole workflow when new code arrives.

## Branch integration tests

A manual branch dispatch with `trigger_pr` naming a real merged code PR and `publish=false` uses Release Please against that branch, maintaining a dedicated test release PR and building a preview. It does not create a final GitHub release or publish to NuGet. A later dispatch should update the same test release PR.

Alternatively, supply an existing `preview_pr` and `trigger_pr` to rebuild that release PR's preview without updating release state. Supply both `release_tag` and `release_sha` to stage a final package against an existing dedicated draft fixture; use `publish=false` for tests. The 0.0.900 draft is dedicated test data, not a NuGet release.

Keep the `nuget-release` environment and deployment rules, `NUGET_USER`, release immutability, and the NuGet trusted publishing policy for `release.yml`. `RELEASE_PLEASE_TOKEN` manages release PRs and drafts. Preview builds have read-only repository access; a separate status job links their artifact from the release PR. Snowflake's workflows remain unchanged during this trial.

Migration resets the manifest baseline to the last published release, 0.1.2; the old draft trials had advanced it to unpublished 0.3.0. Release Please calculates the next proposed version from the published baseline and updates the project version in its release PR.
