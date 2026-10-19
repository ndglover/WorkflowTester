# Single release pipeline trial

WorkflowTester uses one release workflow, release.yml. It runs on relevant pushes to main or manual dispatch. The separate Release Please workflow has been removed.

## Visible stages

1. Prepare release or refresh candidate: process a merged release PR, or maintain the next version/changelog PR if no current draft exists. When the current version is still a draft, select the newest source and refresh that candidate instead of proposing another version.
2. Build candidate: check out the exact planned SHA, check the version, build the package once, and save it as a workflow artifact. Build permissions remain read-only.
3. Stage candidate for testing: update the draft target and generated release notes; attest the actual package source; attach the package and provenance; download and verify them. The summary links to the draft and shows source SHA and digest.
4. Approve and publish to NuGet: wait for the existing nuget-release approval; verify the source, digest, and signed provenance; freeze the candidate; authenticate with OIDC and push that same package.
5. Publish GitHub release: publish the draft, locking its assets and tag when repository immutability is enabled.

## Refresh and approval

A new relevant push while the candidate remains unpublished replaces the draft candidate with a new package, source SHA, release notes, and provenance. The previous waiting approval is superseded. Plan jobs are serialised; draft mutation and NuGet publication share a candidate lock. Superseded source checks prevent old runs from publishing stale candidates.

The publishing job marks publication started before contacting NuGet. Once that marker is set, or the version is found on NuGet, preparation stops rebuilding that version. Resume the original run after a partial publication failure. Subsequent code changes need the next version after this release is finished.

Do not use cancel-in-progress on the whole workflow: that could interrupt a package upload. Automatic supersession targets runs waiting for approval. If approval and supersession cross, the publication marker retains the frozen candidate for recovery.

## Manual branch tests

Supply an existing draft release_tag and matching project-version release_sha, and set publish=false. This runs planning, build and staging without either publication job. Supply both fields together. With no explicit tag, the workflow operates on the current main release state.

The 0.0.900 draft and fixture branch are dedicated test data. They are not NuGet releases. Normal selection follows the manifest version rather than these test fixtures.

## Setup retained

Keep release immutability, the nuget-release environment and main deployment rule, NUGET_USER, and the NuGet trusted-publishing policy for release.yml. RELEASE_PLEASE_TOKEN manages release PRs and exposes drafts to the planning job. The built-in token is used for candidate attachment, attestations, publication, and superseding old waiting runs.

The separate Publish Preview workflow and its preview-only MinVer settings have been removed. Download candidate packages from the draft GitHub release for testing. Snowflake's workflows are unchanged pending review of this trial.