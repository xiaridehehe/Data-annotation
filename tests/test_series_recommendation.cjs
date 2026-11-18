const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('../frontend/node_modules/typescript');

const source = fs.readFileSync('frontend/seriesRecommendation.ts', 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = { exports: {} };
vm.runInNewContext(code, context);
const recommend = context.exports.annotationRecommendation;

for (const description of ['pd_fse_sag_fs', 'OSag PD fs', 'OSag fs PD FSE'])
  assert.deepEqual({ ...recommend({ orientation: 'SAG', description }) }, { plane: 'SAG', planeLabel: '矢状位', weighting: 'PD-FS' });
for (const description of ['pd_fse_cor_fs', 'OCor PD fs', 'OCor fs PD FSE'])
  assert.deepEqual({ ...recommend({ orientation: 'COR', description }) }, { plane: 'COR', planeLabel: '冠状位', weighting: 'PD-FS' });
assert.equal(recommend({ orientation: 'AX', description: 'pd_fse_tra_fs' }).weighting, 'PD-FS');
assert.equal(recommend({ orientation: 'AX', description: 'OAx fs T2 FSE' }).weighting, 'T2-FS');
assert.equal(recommend({ orientation: 'SAG', description: 'T1 FSE' }), null);
assert.equal(recommend({ orientation: 'COR', description: 'T2 FSE' }), null);
assert.equal(recommend({ orientation: 'AX', description: 'PD FSE' }), null);

console.log('Series annotation recommendation checks passed.');
