const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(source, /const localPixelOnly = !!reviewSubmission \|\| pendingAnnotatorReview/);
assert.match(source, /localOnly: localPixelOnly/);
assert.match(source, /expectedStudyUid: localPixelOnly \? activeStudyId/);
assert.match(source, /pendingAnnotatorReview \? [^:]+当前检查保持只读/);
assert.match(source, /editLocked = readOnlyReview \|\| pendingAnnotatorReview/);

console.log('Read-only submitted-study reimport checks passed.');
