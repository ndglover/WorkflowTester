const assert = require('node:assert/strict');
const {test} = require('node:test');
const {parseConventionalCommits} = require('release-please/build/src/commit');
const {DefaultVersioningStrategy} = require('release-please/build/src/versioning-strategies/default');
const {Version} = require('release-please/build/src/version');
const {needsVersionPr} = require('./check-candidate-version.cjs');

function calculate(messages) {
  const commits = parseConventionalCommits(messages.map((message, index) => ({sha: String(index), message})));
  return new DefaultVersioningStrategy().bump(Version.parse('0.1.2'), commits).toString();
}

test('PR #15 breaking-change syntax selects 1.0.0 and pauses the 0.3.0 candidate', () => {
  const proposed = calculate(['feat(api)!: hello again']);
  assert.equal(proposed, '1.0.0');
  assert.equal(needsVersionPr('0.3.0', proposed), true);
});
test('feature-only refresh uses the published baseline instead of incrementing the draft', () => {
  const proposed = calculate(['feat(api): add greeting']);
  assert.equal(proposed, '0.2.0');
  assert.equal(needsVersionPr('0.3.0', proposed), false);
});
test('version calculation converges after the 1.0.0 release PR is merged', () => {
  const proposed = calculate(['feat(api)!: hello again']);
  assert.equal(needsVersionPr('1.0.0', proposed), false);
});
