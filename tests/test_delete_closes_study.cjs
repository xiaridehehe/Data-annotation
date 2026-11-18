const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(source, /\[studyClosed, setStudyClosed\] = S\(false\)/);
assert.match(source, /studyClosed && !reviewSubmission \? ""/);
assert.match(source, /displayedStudies = studyClosed && !reviewSubmission\s*\? \[\]/);
assert.match(source, /if \(studyClosed && !reviewSubmission\) return;/);
assert.match(source, /setStudyClosed\(true\);\s*loadedStudy\.current = "";/);
assert.match(source, /if \(!reviewSubmission\) \{\s*setStudyClosed\(false\);/);

console.log('Delete-current-study blank-state checks passed.');
