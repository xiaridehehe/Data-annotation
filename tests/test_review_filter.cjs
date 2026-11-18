const fs = require('node:fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(source, /reviewFilter[\s\S]*?"ALL"[\s\S]*?"REVIEWED"[\s\S]*?"PENDING"/);
assert.match(source, /item\.status === "SUBMITTED"/);
assert.match(source, /item\.status !== "SUBMITTED"/);
assert.match(source, /\["ALL", "全部", items\.length\]/);
assert.match(source, /\["REVIEWED", "已审核", reviewedCount\]/);
assert.match(source, /\["PENDING", "未审核", pendingCount\]/);
assert.match(source, /visibleItems\.map/);

console.log('Reviewer list filter checks passed.');
