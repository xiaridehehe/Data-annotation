// Exercise the actual TypeScript persistence adapter without a browser viewer.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const ts=require('../frontend/node_modules/typescript');
const source=fs.readFileSync('frontend/local.ts','utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const kinds=['patients','studies','series','instances','diseases','assessments','lesions','boxes','groups','segmentations'];
let server=Object.fromEntries(kinds.map(k=>[k,[]]));server._deleted={lesions:[],boxes:[],assessments:[]};
let requests=[];
const context={exports:{},structuredClone,TextDecoder,TextEncoder,Uint8Array,Map,Set,Promise,Array,JSON,Date,Math,Number,String,Error,Blob,crypto:require('node:crypto').webcrypto,
 localStorage:{getItem:key=>key==='knee-operator'?'tester':'00000000-0000-4000-8000-000000000001'},
 require:name=>name==='@cornerstonejs/dicom-image-loader'?{wadouri:{fileManager:{add:()=>''}}}:name==='dicom-parser'?{parseDicom:()=>{}}:{unzipSync:()=>({})},
 indexedDB:{open(){const r={};setTimeout(()=>{r.result={transaction(){const t={objectStore(){return {openCursor(){const cursor={};setTimeout(()=>{cursor.result=null;cursor.onsuccess();t.oncomplete()},0);return cursor}}}};return t}};r.onsuccess()},0);return r}},
 fetch:async(url,options)=>{
  if(options.method==='GET')return {ok:true,json:async()=>({state:structuredClone(server)})};
  const body=JSON.parse(options.body);requests.push(body);
  const changes=[];
  for(const op of body.operations){let old=server[op.kind].find(x=>x.id===op.record.id)||server._deleted[op.kind]?.find(x=>x.id===op.record.id);if((old?.version||0)!==op.expected_version)return {ok:false,status:409,text:async()=>JSON.stringify({detail:'版本冲突'})};
   const version=(old?.version||0)+1;server[op.kind]=server[op.kind].filter(x=>x.id!==op.record.id);
   if(op.action==='delete'){server._deleted[op.kind].push({...old,version})}else{server[op.kind].push({...op.record,version});if(server._deleted[op.kind])server._deleted[op.kind]=server._deleted[op.kind].filter(x=>x.id!==op.record.id)}changes.push({kind:op.kind,id:op.record.id,version});}
  return {ok:true,json:async()=>({changes,saved_at:'2026-11-13T00:00:00Z'})}
 }};
vm.runInNewContext(code,context);
(async()=>{
 const {req}=context.exports;
 await req('/state');
 await req('/lesions','PUT',{id:'lesion',series_id:'series',disease_type_id:'ACL_INJURY',attributes_json:{}});
 assert.equal(requests.at(-1).operations.length,1);
 assert.equal(requests.at(-1).operations[0].kind,'lesions');
 await req('/assessments','PUT',{series_id:'series',disease_type_id:'MENISCUS_INJURY',target_key:'MEDIAL_MENISCUS',attributes_json:{severity:'partial'}});
 await req('/assessments','PUT',{series_id:'series',disease_type_id:'MENISCUS_INJURY',target_key:'LATERAL_MENISCUS',attributes_json:{severity:'normal'}});
 assert.equal(server.assessments.length,2);
 await req('/lesions/lesion','DELETE');
 await req('/state');
 await req('/lesions','PUT',{id:'lesion',series_id:'series',disease_type_id:'ACL_INJURY',attributes_json:{}});
 assert.equal(requests.at(-1).operations[0].expected_version,2);
 server.lesions[0].version++;
 await assert.rejects(req('/lesions','PUT',{...server.lesions[0],color:'#000000'}),/版本冲突/);
 const saved=await req('/project/save','POST');assert.ok(saved.saved_at);
 console.log('Frontend persistence checks passed: deltas, separate sides, restore, stale conflict, save.');
})().catch(e=>{console.error(e);process.exitCode=1});
