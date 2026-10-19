'use strict';

const {appendFileSync} = require('node:fs');
const {GitHub, Manifest} = require('release-please');
const {Version} = require('release-please/build/src/version');

const packagePath = 'src/WorkflowTester.Lib';

function needsVersionPr(current, proposed) {
  // A previously selected draft version is a floor; never downgrade it.
  return proposed && Version.parse(proposed).compare(Version.parse(current)) > 0;
}

async function main() {
  const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
  const token = process.env.GH_TOKEN;
  const branch = 'main';
  const github = await GitHub.create({owner, repo, token});
  const manifest = await Manifest.fromManifest(github, branch);
  const current = manifest.releasedVersions[packagePath].toString();

  // The committed manifest can describe an unpublished draft. Use the last
  // published version as Release Please's baseline, rather than bumping the
  // draft again on every push (which would recreate the release-PR loop).
  const published = [];
  for (let page = 1; ; page++) {
    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/releases?per_page=100&page=${page}`, {
      headers: {Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json'},
    });
    if (!response.ok) throw new Error(`Cannot read releases: ${response.status}`);
    const releases = await response.json();
    for (const release of releases) {
      if (!release.draft && !release.prerelease && /^dotnet\/v\d+\.\d+\.\d+$/.test(release.tag_name)) {
        published.push(Version.parse(release.tag_name.slice('dotnet/v'.length)));
      }
    }
    if (releases.length < 100) break;
  }
  published.sort((a, b) => b.compare(a));
  if (!published.length) throw new Error('Cannot recalculate a draft without a published baseline.');
  manifest.releasedVersions[packagePath] = published[0];
  const candidates = await manifest.buildPullRequests();
  if (candidates.length > 1) throw new Error('Expected one component release PR.');
  const proposed = candidates[0]?.version?.toString();
  const needsPr = Boolean(needsVersionPr(current, proposed));
  const summary = `Published baseline: ${published[0]}; committed candidate: ${current}; calculated version: ${proposed || 'unchanged'}.`;
  console.log(summary);
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT, `needs_pr=${needsPr}\nversion=${needsPr ? proposed : current}\n`);
  }
  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${summary}\n\n${needsPr ? 'Candidate staging is paused until the version/changelog release PR is merged.' : 'The candidate version already covers the accumulated changes.'}\n`);
  }
  if (needsPr && process.argv.includes('--apply')) {
    // Refuse to update the PR from a calculation overtaken by another main push.
    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/ref/heads/main`, {
      headers: {Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json'},
    });
    if (!response.ok) throw new Error(`Cannot verify main: ${response.status}`);
    if ((await response.json()).object.sha !== process.env.GITHUB_SHA) {
      throw new Error('Main advanced during version calculation; use the newest run.');
    }
    const prs = await manifest.createPullRequests();
    if (!prs.some(Boolean)) {
      // Release Please returns undefined when an existing PR is unchanged.
      let existing;
      for await (const pr of github.pullRequestIterator(branch, 'OPEN', 200, false)) {
        if (pr.headBranchName === candidates[0].headRefName && pr.title === candidates[0].title.toString()) {
          existing = pr;
          break;
        }
      }
      if (!existing) throw new Error('Version update required but no matching release PR exists.');
      prs.push(existing);
    }
    console.log(`Version release PR: ${prs.filter(Boolean).map(pr => pr.number).join(', ')}`);
  }
}

module.exports = {needsVersionPr};
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
