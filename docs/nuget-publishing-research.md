# Publishing NuGet packages from a Go + C# GitHub repo

Historical research notes. The current trial uses the single release pipeline described in [snowflake-release-parity.md](snowflake-release-parity.md); the separate PR preview publishing workflow has been removed.

---

## The original question

> I have a github repo with some Go code and some C# code. I want to add some workflows to publish nuget packages for the C# code. Before we go ahead and do that I'd like you to go away and do some research on the best practices for this kind of thing. One thing that would be ideal is the ability to publish pre-release packages that can be driven from Pull Requests. The main reason for this is to allow people to test the library with their code base using a normal developer workflow, so there may be better ways to do this? Ideally you should reference existing github projects that have similar workflows. We will need some controls over who can run these workflows.

**Follow-up constraint:** the repo is **public**, and the consumers are **corporates**.

---

## Summary of the recommendation

Three publishing tiers, with different triggers, different credentials and different approval gates.

| Tier | What | Destination | Trigger | Gate |
|---|---|---|---|---|
| 1 | Stable release | nuget.org | `dotnet/v*` tag | Environment with required reviewers + tag ruleset |
| 2 | Deliberate preview (`1.4.0-preview.3`) | nuget.org | `workflow_dispatch` with a PR number | Environment with required reviewers |
| 3 | Per-push PR build (`1.4.0-pr.123.4`) | Public anonymous feed + build artifact | `pull_request` label, opt-in | Environment approval before publish |

The key insight for corporate consumers: **their package proxy is the binding constraint, not your pipeline.** Corporate devs typically resolve through Artifactory, Nexus or Azure Artifacts, which mirror nuget.org. Adding a new upstream feed usually needs a security ticket. So any preview channel other than nuget.org starts with friction for exactly the people you most want testing the library.

---

## Tier 1 and 2: nuget.org via Trusted Publishing

Trusted Publishing is now the standard. No stored API keys: the workflow uses a short-lived GitHub OIDC token to request a temporary, single-use nuget.org API key that expires after about an hour.

Mechanics:

- `permissions: id-token: write` on the publish job.
- A `NuGet/login@v1` step mints the short-lived key; `dotnet nuget push` consumes it.
- The nuget.org policy binds to a specific repo **and workflow filename**, and optionally a GitHub environment.
- Private-repo gotcha (not applicable here, but worth knowing): new policies start active for only 7 days, then become permanently active after the first successful login.

Access control comes from the environment binding:

- Publish job runs in an environment with **required reviewers** and **prevent self-review** enabled.
- Restrict the environment to the release tag pattern.
- Add a **tag ruleset** so only release managers can create `dotnet/v*` tags.
- Result: a compromised or careless workflow edit cannot publish without a human approval.

### Tier 2 specifically

Publishing *every PR push* to nuget.org is wrong: versions are permanent, and the version list gets polluted. But an occasional, maintainer-cut preview is different, and it is the only channel corporate testers consume with zero friction.

- `workflow_dispatch` input takes the PR number.
- Runs in its own `nuget-preview` environment with required reviewers.
- Bound to the same trusted publishing policy.
- Posts the resulting version back to the PR as a comment.
- Trade-off: each preview lives forever (unlisted at best). Acceptable if infrequent and intentional.

### References

- Andrew Lock, full setup walkthrough including the 401 you hit before the policy activates: https://andrewlock.net/easily-publishing-nuget-packages-from-github-actions-with-trusted-publishing/
- .NET blog announcement: https://devblogs.microsoft.com/dotnet/enhanced-security-is-here-with-the-new-trust-publishing-on-nuget-org/
- James Croft, end-to-end workflow with Source Link and symbols: https://www.jamescroft.co.uk/how-to-build-publish-nuget-packages-with-github-actions/
- Environment-bound variant (ShellSyntaxTree PR #11): https://github.com/Aaronontheweb/ShellSyntaxTree/pull/11
- Microsoft docs: https://learn.microsoft.com/nuget/nuget-org/trusted-publishing

---

## Versioning in a Go + C# repo: tag prefixes are mandatory

If a Go module sits at the repo root, Go treats bare `vX.Y.Z` tags as **its** versions. C# release tags must not collide.

MinVer handles this:

- Tag C# releases as `dotnet/v1.2.0`.
- Set `<MinVerTagPrefix>dotnet/v</MinVerTagPrefix>` so MinVer only considers matching tags.
- Between tags MinVer bumps the patch, adds a pre-release phase and appends "height" (commits since tag), e.g. `1.0.1-alpha.0.42`.
- Add MinVer once in `Directory.Build.targets` for every packable project, with `PrivateAssets="all"`.
- Floor the version with `MinVerMinimumMajorMinor` so pre-tag CI builds don't look like a regression to 0.x.
- For PR builds, override the version to something explicit like `1.3.0-pr.123.4` (PR number + run number) so provenance is obvious.

Reference (monorepo, per-package tag prefixes, MinVer + trusted publishing):
https://startdebugging.net/2026/05/independently-release-multiple-nuget-packages-with-minver-and-trusted-publishing/

Note on SemVer ordering: pre-release identifiers sort alphanumerically, so `pr` sorts above `alpha` and below `preview`/`rc`. Check that floating version ranges in consumer projects can't accidentally pick up PR builds. Avalonia sidesteps this by using a `.999` patch on CI builds so they always sort above real releases.

---

## Tier 3: per-push PR builds

Goal: let someone test an unmerged PR through a normal `dotnet add package` workflow.

### Channel comparison

| Channel | Consumer friction | Verdict |
|---|---|---|
| nuget.org, every PR push | None | No. Versions can't be deleted, only unlisted. Permanent noise. |
| Build artifact (`.nupkg` download + local folder feed) | Medium, manual | Always ship this as a baseline. Zero infra, zero security surface. Locked-down shops often prefer it: they upload into their own internal feed. |
| GitHub Packages | Auth always required | **Not for this audience.** NuGet on GitHub Packages requires a token even for public packages (only the container registry allows anonymous pulls), and only classic PATs work. Corporate devs can't put personal tokens in a shared nuget.config. |
| Public anonymous feed (feedz.io, Cloudsmith, self-hosted BaGet) | Low | Best experience. What mature projects do. |

A public feedz.io repository works without credentials, and feedz retention rules automatically prune old versions as new ones arrive, which solves PR cleanup.

### Reference implementations

- **Avalonia** — the closest match to what was asked for. A bot comments on every PR: "You can test this PR using the following package version. 11.0.999-cibuild0037780-beta" plus the feed URL. They self-host a BaGet feed for nightly/PR builds. The bot comment means testers never have to work out which version to install. Example: https://github.com/AvaloniaUI/Avalonia/pull/12216
- **Elsa Workflows** — clean split of preview vs release in one workflow file: feedz.io on push or release, nuget.org only on release. https://github.com/elsa-workflows/elsa-studio
- **Foundatio** — CI builds to feedz.io versioned `1.0.0-preview.12345+sha.abcdef`, documented nuget.config with package source mapping.
- **ForEvolve/EzTelemetry** — documents a credential-free public feedz source in a checked-in nuget.config: https://github.com/forevolve/eztelemetry
- **ServiceStack** — publishes interim pre-releases to GitHub Packages, feedz and MyGet; docs show the PAT friction GitHub Packages imposes: https://docs.servicestack.net/gh-nuget
- **matt-goldman/blake** — small, clean example of label-driven publishing (`preview` and `release` labels): https://github.com/matt-goldman/blake
- **Meziantou.Analyzer PR #1380** — removed always-on Feedz publishing of non-main CI builds. A useful counter-signal: always-on preview publishing has an ongoing cost.

---

## Security model

**Core rule: never check out and build PR code in a workflow that holds secrets or write permissions.**

Combining `pull_request_target` with a checkout of untrusted PR code is the "pwn request" pattern and can lead to full repository compromise. This is not theoretical: the Nx "s1ngularity" campaign and the PostHog and TanStack breaches all used it. `actions/checkout@v7` now blocks fetching unreviewed fork PR code under `pull_request_target` or `workflow_run` unless you explicitly opt out with `allow-unsafe-pr-checkout`. GitHub also warns that `issue_comment` and `workflow_run` workflows are vulnerable the same way, and that artifacts produced by fork runs must be treated as untrusted data.

- GitHub Security Lab: https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/
- GitHub docs: https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target

### Job structure

1. **Build job** — plain `pull_request` trigger, read-only token, no secrets. Build, test, pack, upload `.nupkg` as an artifact. Runs on every PR.
2. **Publish job (opt-in)** — triggered by a `publish-preview` label or a `workflow_dispatch` taking a PR number. Both require write/triage access, so drive-by contributors can't trigger publishing. Prefer opt-in over publish-on-every-push: most PRs don't need a package, and it keeps the feed clean.
3. **Environment gate** — the publish job runs in a `preview-packages` environment holding the feed credential, requiring approval from a named team. This matters because in a public repo a preview package built from a fork is **attacker-authored code shipped under your package name**. The reviewer must approve the diff, not just the label.
4. **Fork workflow approval** — enable "require approval for all external contributors" so fork PRs don't run CI unattended.
5. **Credential separation** — the preview feed key lives only in the tier 3 environment; the nuget.org trusted publishing policy binds only to the tier 1 and 2 environments and workflow files.

### Hygiene

- `CODEOWNERS` on `.github/workflows/`.
- Pin third-party actions by commit SHA.
- Minimal `permissions:` per job, declared explicitly.
- Never interpolate PR titles or branch names into `run:` scripts (script injection).
- Clean up PR package versions when the PR closes (feedz retention rules, or the delete-package-versions action for GitHub Packages).

---

## Things corporate consumers will care about

Beyond the workflows, these affect adoption:

- **Reserve the package ID prefix on nuget.org** — gives the verified tick, prevents squatting, and lets consumers apply package source mapping safely (maps your IDs to your feed, blocking dependency-confusion attacks from the preview feed).
- **Source Link, deterministic builds (`ContinuousIntegrationBuild=true`), and `.snupkg` symbol packages** — lets their developers debug into your code. Note: nuget.org rejects symbol packages containing PDBs for assemblies outside `lib/`, so analyzers and build tasks need embedded PDBs instead.
- **Build provenance attestations** (`actions/attest-build-provenance`) — lets a security team verify a package was built from your repo at a given commit. Increasingly requested.
- **Strong naming** — worth doing if any consumers are still on .NET Framework.
- **A checked-in `nuget.config` sample** in the README for the preview feed, with package source mapping, so consumers copy rather than improvise.

---

## Implementation checklist

- [ ] `Directory.Build.props` / `.targets`: MinVer with `MinVerTagPrefix`, package metadata, Source Link, deterministic builds, symbol package generation, `IsPackable` defaults.
- [ ] `ci.yml` — build/test/pack on `pull_request` and `push` to main. No secrets. Uploads `.nupkg` artifact.
- [ ] `publish-preview.yml` — tier 3. Label or dispatch triggered, environment-gated, pushes to the preview feed, comments the version and install snippet back on the PR.
- [ ] `publish-nuget-preview.yml` — tier 2. `workflow_dispatch` with PR number, environment-gated, trusted publishing.
- [ ] `release.yml` — tier 1. Triggered by `dotnet/v*` tag, environment-gated, trusted publishing, creates the GitHub release.
- [ ] GitHub environments: `nuget-release`, `nuget-preview`, `preview-packages` — required reviewers, prevent self-review, branch/tag restrictions.
- [ ] Tag ruleset for `dotnet/v*`.
- [ ] `CODEOWNERS` covering `.github/`.
- [ ] nuget.org trusted publishing policies (one per publishing workflow file).
- [ ] Preview feed account (feedz.io free plan) + retention rule + API key in the tier 3 environment.
- [ ] README section: how to consume a PR preview.

---

## Open decisions

1. **Preview feed choice** — feedz.io public repo is the closest fit. Cloudsmith and self-hosted BaGet (Avalonia's choice) are alternatives. Could start with artifacts only and add the feed later.
2. **Whether tier 2 is worth the permanent nuget.org versions** — depends on how often external corporates actually need to test unmerged work. If rarely, tier 3 plus a manual upload path may be enough.
3. **Repo layout** — where the Go module sits determines the tag prefix scheme and the path filters on the workflows.
4. **Package ID prefix** — decide and reserve before the first publish; renaming afterwards is painful.
