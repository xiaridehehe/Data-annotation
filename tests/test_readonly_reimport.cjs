const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(source, /await workflowRequest\("\/submissions"\)/);
assert.match(source, /filter\(\(item\) => item\.status === "SUBMITTED"\)/);
assert.match(source, /localOnly: !!reviewSubmission/);
assert.match(source, /expectedStudyUid: reviewSubmission \? importStudyId/);
assert.match(source, /readOnlyStudyUids/);
assert.match(source, /importedReadOnly \? [^:]+当前检查保持只读/);
assert.match(source, /editLocked = readOnlyReview \|\| pendingAnnotatorReview/);

const local = fs.readFileSync('frontend/local.ts', 'utf8');
assert.match(local, /readOnlyStudyUids = new Set\(options\.readOnlyStudyUids \|\| \[\]\)/);
assert.match(local, /if \(readOnlyStudyUids\.has\(study\)\) importedReadOnlyStudyIds\.add\(study\)/);
assert.match(local, /series_uids: Array\.from\(writableSeriesIds\)/);
assert.match(local, /writableStudyIds\.has\(item\.id\)/);

console.log('Read-only submitted-study reimport checks passed.');
