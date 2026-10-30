# NuGet duplicate verification investigation

Investigated 30 October 2026 on `codex/workflowtester-nuget-content-verification`.
Snowflake is unchanged. The original mini C# project has been removed, including
its generated build directories. The implementation now uses built-in commands.

## Current workflow implementation

The existing .NET 8 package build is unchanged. Only the `publish_nuget` job sets
up .NET 10, whose `dotnet nuget verify` command reports a signature-independent
package content hash.

The publication sequence is now:

1. Download and verify the approved GitHub assets as before.
2. Freeze the candidate and obtain the short-lived NuGet key as before.
3. Push the main package, retaining `--skip-duplicate --no-symbols`.
4. Discover NuGet's package content endpoint from its service index and download
   the published version. A bounded retry window handles processing delays.
5. Run `dotnet nuget verify --all --verbosity normal` and require success.
6. Require exactly one reported content hash and compare it to the SHA-512 of
   our original unsigned package. This accounts for NuGet repository signing.
7. Only then push the symbols and allow GitHub release publication.

The check runs after fresh uploads and duplicate responses, covering a race with
another publisher. It is inside the NuGet publishing job so that job cannot
succeed without verification. Hash mismatch, missing/ambiguous output, invalid
signature, malformed package, or exhausted download retries stop publication.
A successful main upload is not rolled back on a later verification failure;
retry the original run after resolving the problem.

The CLI language is fixed to English because the workflow reads its content-hash
line. Missing output after a future CLI formatting change fails closed. This is
a text-output dependency rather than a custom NuGet library dependency.

The expected hash assumes our approved package is unsigned, as in our current
build. Introducing author signing would require revisiting that calculation.
The comparison covers the main `.nupkg`; it does not independently compare the
symbol package already on NuGet's symbol service.

## Validation

The tests extract and execute the actual verification step from
`.github/workflows/csharp_release.yaml`; there is no separate production utility.
The fixed fixtures are the actual GitHub release asset and NuGet copy of
`WorkflowTester.Lib` 3.0.0. No new package is published by these tests.

```text
python .github/release-tools/test-nuget-verification.py
```

Requires Python 3, .NET 10, bash, curl, jq and openssl (available on the Ubuntu
Actions runner after setting up .NET). Fixture download uses only public URLs.
`--fixtures DIRECTORY` can reuse an existing fixture directory containing
`approved.3.0.0.nupkg` and `published.3.0.0.nupkg`.

Cases include a real NuGet download and successful match, raw signed archive
hashes differing, matching signed content, conflicting DLL or nuspec content,
tampered signatures, unsigned or malformed downloads, transport/service-index
failures, a missing approved file, and missing/ambiguous CLI hash output.
Transport is simulated for error cases; actual signature verification runs.
Only CLI output-format tests substitute a fake dotnet command.

This does not send an actual duplicate push. A full approved publication still
requires the normal environment approval.

Sources:

- [.NET 10 content-hash output](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-nuget-verify)
- [NuGet repository signatures](https://devblogs.microsoft.com/dotnet/introducing-repository-signatures/)
- [Official content hash implementation](https://github.com/NuGet/NuGet.Client/blob/dev/src/NuGet.Core/NuGet.Packaging/PackageArchiveReader.cs)
- [Package content API](https://learn.microsoft.com/en-us/nuget/api/package-base-address-resource)

## Public repository evidence

These are pinned snapshots of actual public publishing paths, not inferred from
project popularity or CI build steps. Followed workflow calls into their scripts.
No reviewed path below downloads an existing NuGet package and compares its
content to the approved artifact before accepting a duplicate.

| Project | Observed publication behavior | Evidence |
| --- | --- | --- |
| Apache Arrow ADBC | Downloads approved release packages, then plain `dotnet nuget push`; no skip-duplicate or custom content comparison in this script. | [post-07-csharp.sh, lines 48-74](https://github.com/apache/arrow-adbc/blob/aa2c1c2496d287e111d70d382e5d9af07568488b/dev/release/post-07-csharp.sh#L48-L74) |
| Dapper | Explicitly uses `--skip-duplicate` to make partially completed pushes rerunnable; no remote content comparison in that path. | [release.yml, lines 91-115](https://github.com/DapperLib/Dapper/blob/eb47546a408bbf6c178bda4f04dc205bc51ffbfe/.github/workflows/release.yml#L91-L115) |
| AutoMapper | Push helper uses `--skip-duplicate`; release workflow calls it for NuGet. | [Push.ps1](https://github.com/AutoMapper/AutoMapper/blob/df65f2e318d3339acf1a5c44f5647fec0ca175c8/Push.ps1), [caller](https://github.com/AutoMapper/AutoMapper/blob/df65f2e318d3339acf1a5c44f5647fec0ca175c8/.github/workflows/release.yml#L112-L116) |
| Polly | Signs and validates packages, then publishes with `--skip-duplicate`; separate indexing wait is not a duplicate-content comparison. | [build.yml, lines 418-465](https://github.com/App-vNext/Polly/blob/31d7ac300743b10163d00ef72fccea88f3acabad/.github/workflows/build.yml#L418-L465) |
| Serilog | Plain `dotnet nuget push`; nonzero exit fails the script. | [Build.ps1, lines 60-75](https://github.com/serilog/serilog/blob/43105b35095337d77f022561a8f2d3db2f9a7937/Build.ps1#L60-L75) |
| Refit | Pushes signed artifacts without `--skip-duplicate` in the inspected NuGet job. | [release.yml, lines 51-81](https://github.com/reactiveui/refit/blob/92ae878250798dc103a01304704a99bb8033ed77/.github/workflows/release.yml#L51-L81) |

Newtonsoft.Json and FluentValidation were also inspected, but the public files
examined did not establish their complete NuGet upload path. They are excluded
from the comparison rather than counted as evidence of no check. Microsoft runtime
publishing is substantially more indirect and is also excluded from this small
comparison.

This is a purposive sample, not a prevalence estimate or proof that no project
implements the reviewer's check. Plain-push examples fail rather than accept a
conflicting duplicate, so they do not demonstrate the same retry guarantee.
