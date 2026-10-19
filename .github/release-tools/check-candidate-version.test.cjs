const assert = require('node:assert/strict');
const {test} = require('node:test');
const {needsVersionPr} = require('./check-candidate-version.cjs');

test('accumulated breaking change supersedes the selected draft version', () => {
  assert.equal(needsVersionPr('0.3.0', '1.0.0'), true);
});
test('ordinary refresh never downgrades or repeatedly bumps the draft', () => {
  assert.equal(needsVersionPr('0.3.0', '0.2.0'), false);
  assert.equal(needsVersionPr('0.3.0', '0.3.0'), false);
});
test('merging the version PR makes subsequent runs converge', () => {
  assert.equal(needsVersionPr('1.0.0', '1.0.0'), false);
  assert.equal(Boolean(needsVersionPr('1.0.0', undefined)), false);
});
