const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(source, /await workflowRequest\("\/submissions"\)/);
assert.match(source, /item\.study_uid === importStudyId && item\.status === "SUBMITTED"/);
assert.match(source, /localPixelOnly = !!reviewSubmission \|\| submittedReadOnly/);
assert.match(source, /localOnly: localPixelOnly/);
assert.match(source, /expectedStudyUid: localPixelOnly \? importStudyId/);
assert.match(source, /submittedReadOnly \? [^:]+当前检查保持只读/);
assert.match(source, /editLocked = readOnlyReview \|\| pendingAnnotatorReview/);

console.log('Read-only submitted-study reimport checks passed.');
