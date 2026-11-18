const fs = require('node:fs');
const assert = require('node:assert/strict');

const local = fs.readFileSync('frontend/local.ts', 'utf8');
const main = fs.readFileSync('frontend/main.tsx', 'utf8');

assert.match(local, /function cacheImages\(items:/);
assert.match(local, /for \(let \{ uid, file \} of items\) store\.put\(file, uid\)/);
assert.doesNotMatch(local, /await cacheImage\(uid, f\)/);
assert.match(local, /new Map<string, number>\([\s\S]*?s\[kind\]/);
assert.match(local, /Promise\.all\([\s\S]*workerCount/);
assert.match(local, /Math\.min\(8, Math\.max\(4, navigator\.hardwareConcurrency \|\| 4\)\)/);
assert.match(local, /正在扫描文件/);
assert.match(local, /正在解析元数据/);
assert.match(local, /正在写入本地缓存/);
assert.match(main, /正在加载首张影像/);
assert.match(main, /maxWebWorkers:[\s\S]*navigator\.hardwareConcurrency/);

console.log('DICOM import performance checks passed.');
