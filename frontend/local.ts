import {parseDicom} from 'dicom-parser';
import {wadouri} from '@cornerstonejs/dicom-image-loader';
import {unzipSync} from 'fflate';
export function repairText(value:string){if(!value||![...value].every(c=>c.charCodeAt(0)<=255))return value;try{return new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(value,c=>c.charCodeAt(0)))}catch{return value}}
function dicomText(ds,tag){let element=ds.elements[tag];if(!element)return '';let bytes=ds.byteArray.subarray(element.dataOffset,element.dataOffset+element.length);let charset=(ds.string('x00080005')||'').trim();let encoding=charset.includes('192')?'utf-8':/GB18030|GBK|IR 58/.test(charset)?'gb18030':charset.includes('100')?'iso-8859-1':charset.includes('149')?'euc-kr':charset.includes('13')||charset.includes('87')?'iso-2022-jp':'utf-8';try{return new TextDecoder(encoding,{fatal:true}).decode(bytes).replace(/[\0 ]+$/g,'')}catch{try{return new TextDecoder('gb18030',{fatal:true}).decode(bytes).replace(/[\0 ]+$/g,'')}catch{return ds.string(tag)||''}}}
const kinds=['patients','studies','series','instances','diseases','assessments','lesions','boxes','groups','segmentations'];
const files=new Map<string,string>();
let dbPromise:Promise<IDBDatabase>;
function db(){return dbPromise ||= new Promise((resolve,reject)=>{let r=indexedDB.open('knee-local-v1',2);r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains('state'))r.result.createObjectStore('state');if(!r.result.objectStoreNames.contains('dicom'))r.result.createObjectStore('dicom')};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}
async function cacheImage(uid:string,file:File){let d=await db();await new Promise<void>((resolve,reject)=>{let t=d.transaction('dicom','readwrite');t.objectStore('dicom').put(file,uid);t.oncomplete=()=>resolve();t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error)})}
let restored:Promise<void>;
function restoreImages(){return restored ||= (async()=>{let d=await db();await new Promise<void>((resolve,reject)=>{let t=d.transaction('dicom'),r=t.objectStore('dicom').openCursor();r.onsuccess=()=>{let cursor=r.result;if(cursor){if(!files.has(String(cursor.key)))files.set(String(cursor.key),wadouri.fileManager.add(cursor.value));cursor.continue()}};t.oncomplete=()=>resolve();t.onerror=()=>reject(t.error)})})()}
function workspace(){return '00000000-0000-4000-8000-000000000001'}
export function operatorName(){return localStorage.getItem('knee-operator')||''}
export function setOperatorName(value:string){localStorage.setItem('knee-operator',value.trim())}

let currentState:any;
const knownVersions=new Map<string,number>();
async function remote(path:string,body?){if(body&&!operatorName().trim())throw Error('请先填写姓名或工号');let r=await fetch('/api/workspaces/'+workspace()+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Operator':encodeURIComponent(operatorName())},body:body?JSON.stringify(body):undefined});if(!r.ok){let raw=await r.text();let detail='';try{detail=JSON.parse(raw).detail||''}catch{}throw Error(detail||(r.status>=500?'服务器处理失败（HTTP '+r.status+'），请检查后端日志和数据库表结构':'请求失败（HTTP '+r.status+'）'))}return r.json()}
async function read(force=false){await restoreImages();if(force||!currentState){let result=await remote('/state');currentState=result.state;for(let k of kinds)for(let item of [...(currentState[k]||[]),...(currentState._deleted?.[k]||[])])knownVersions.set(k+':'+item.id,item.version)}return structuredClone(currentState)}
async function write(s){let operations=[];for(let k of kinds){if(['groups','segmentations'].includes(k))continue;let old=new Map<string,any>((currentState[k]||[]).map(x=>[x.id,x]));for(let item of s[k]||[]){let before=old.get(item.id);if(!before||JSON.stringify(before)!==JSON.stringify(item))operations.push({kind:k,action:'upsert',record:item,expected_version:before?.version??knownVersions.get(k+':'+item.id)??0});old.delete(item.id)}for(let item of old.values())operations.push({kind:k,action:'delete',record:{id:item.id},expected_version:item.version})}
 // Each ordinary edit is one short transaction. Imports are committed in bounded batches.
 let saved_at=new Date().toISOString();for(let start=0;start<operations.length;start+=1000){let result;try{result=await remote('/changes',{operations:operations.slice(start,start+1000)})}catch(error){currentState=undefined;throw error}saved_at=result.saved_at;for(let change of result.changes){knownVersions.set(change.kind+':'+change.id,change.version);let item=s[change.kind].find(x=>x.id===change.id);if(item)item.version=change.version;
 else if(['assessments','lesions','boxes'].includes(change.kind)){let removed=currentState[change.kind].find(x=>x.id===change.id);if(removed){s._deleted ||= {};s._deleted[change.kind] ||= [];s._deleted[change.kind]=s._deleted[change.kind].filter(x=>x.id!==change.id);s._deleted[change.kind].push({...removed,version:change.version})}}
 if(item&&s._deleted?.[change.kind])s._deleted[change.kind]=s._deleted[change.kind].filter(x=>x.id!==change.id)}}
 currentState=structuredClone(s);return {saved_at}}
let queue=Promise.resolve();
function upsert(s,k,d){let i=s[k].findIndex(x=>x.id===d.id);if(i<0)s[k].push(d);else s[k][i]=d;return d}
export function imageId(uid){let id=files.get(uid);if(!id)throw Error('请重新选择本地影像文件，已有标注会自动载入');return id}
export function req(path,method='GET',data?):Promise<any>{let task=queue.then(async()=>{let s=await read(path==='/state'),p=path.split('/').filter(Boolean).map(decodeURIComponent),result:any;
 if(path==='/state')return s;
 if(p[0]==='imported'){
 if(p[1]==='restore'){let info=JSON.parse(p.slice(2).join('/'));let result=await remote('/visibility',{kind:info.kind,id:info.id,expected_version:info.version,restore:true});currentState=undefined;return result}
 let item=s[p[1]]?.find(x=>x.id===p[2]);if(!item)throw Error('数据不存在');let result=await remote('/visibility',{kind:p[1],id:p[2],expected_version:item.version,restore:false});currentState=undefined;return result
 }
 if(method==='PUT'){
 let k=p[0],d={...data};d.id ||= crypto.randomUUID();
 if(k==='assessments'&&!d.series_id)throw Error('整体评估必须选择序列');
 if(k==='assessments'){d.target_key=d.disease_type_id==='MENISCUS_INJURY'?d.target_key:'OVERALL';d.id=[d.series_id,d.disease_type_id,d.target_key].join('|')}
 if(k==='lesions')d.color=s.lesions.find(x=>x.id===d.id)?.color||d.color||'#'+crypto.randomUUID().replaceAll('-','').slice(0,6);
 if(k==='boxes'){let l=s.lesions.find(x=>x.id===d.lesion_instance_id),im=s.instances.find(x=>x.id===d.sop_instance_uid);if(!l||!im||l.series_id!==im.series_id)throw Error('序列不匹配');if(!(0<=d.x_min&&d.x_min<d.x_max&&d.x_max<=im.width&&0<=d.y_min&&d.y_min<d.y_max&&d.y_max<=im.height))throw Error('框坐标越界');d.id=[...s.boxes,...(s._deleted?.boxes||[])].find(x=>x.lesion_instance_id===l.id&&x.sop_instance_uid===im.id)?.id||d.id}
 result=upsert(s,k,d);
 }else if(path==='/project/save'){return remote('/changes',{operations:[]});
 }else if(p[0]==='slices'){let deleted=s.boxes.filter(b=>b.sop_instance_uid===p[1]);s.boxes=s.boxes.filter(b=>b.sop_instance_uid!==p[1]);result={deleted,count:deleted.length};
 }else if(method==='DELETE'){s[p[0]]=s[p[0]].filter(x=>x.id!==p[1]);if(p[0]==='lesions')s.boxes=s.boxes.filter(b=>b.lesion_instance_id!==p[1]);result={ok:true}
 }else throw Error('不支持的本地操作');await write(s);return result});queue=task.then(()=>undefined,()=>undefined);return task}
export async function importLocal(input:FileList|File[]){let entries:File[]=[];for(let f of Array.from(input)){if(f.name.toLowerCase().endsWith('.zip')){let zip=unzipSync(new Uint8Array(await f.arrayBuffer()));for(let [name,bytes] of Object.entries(zip))if(!name.endsWith('/'))entries.push(new File([bytes as BlobPart],name))}else entries.push(f)}
 let task=queue.then(async()=>{let s=await read(),count=0,errors=[],uids=new Set(),seriesIds=new Set(),studyIds=new Set();for(let f of entries)try{
 let ds=parseDicom(new Uint8Array(await f.arrayBuffer()));if(!ds.elements.x7fe00010)continue;if(Number(ds.string('x00280008')||1)>1)throw Error('暂不支持多帧 DICOM，请导入单帧影像');
 let val=t=>ds.string(t)||'',uid=val('x00080018'),study=val('x0020000d'),series=val('x0020000e'),patientCode=dicomText(ds,'x00100020'),issuer=dicomText(ds,'x00100021')||dicomText(ds,'x00080080'),patientSeed=patientCode&&issuer?issuer+'|'+patientCode:'study|'+study,patient=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(patientSeed)))).map(x=>x.toString(16).padStart(2,'0')).join('');if(!uid||!study||!series)throw Error('缺少 DICOM UID');
 let orient=val('x00200037').split('\\').filter(Boolean).map(Number),pos=val('x00200032').split('\\').filter(Boolean).map(Number),order=Number(val('x00200013'))||0,axis='未知';if(orient.length===6&&pos.length===3){let [a,b,c,d,e,g]=orient,n=[b*g-c*e,c*d-a*g,a*e-b*d];order=n.reduce((v,x,i)=>v+x*pos[i],0);axis=['SAG','COR','AX'][n.map(Math.abs).indexOf(Math.max(...n.map(Math.abs)))]}
 upsert(s,'patients',{...s.patients.find(x=>x.id===patient),id:patient,patient_code:patientCode||null,issuer:issuer||null});upsert(s,'studies',{id:study,patient_id:patient,description:dicomText(ds,'x00081030'),date:val('x00080020'),study_time:val('x00080030'),accession_number:val('x00080050')});upsert(s,'series',{id:series,study_id:study,description:dicomText(ds,'x0008103e')||dicomText(ds,'x00181030')||'未命名序列',number:val('x00200011'),orientation:axis,modality:val('x00080060')||'MR'});upsert(s,'instances',{id:uid,series_id:series,width:ds.uint16('x00280011'),height:ds.uint16('x00280010'),order,instance_number:Number(val('x00200013'))||null,position:pos,orientation:orient,pixel_spacing:val('x00280030').split('\\').filter(Boolean).map(Number),metadata:{}});
 await cacheImage(uid,f);files.set(uid,wadouri.fileManager.add(f));uids.add(uid);seriesIds.add(series);studyIds.add(study);count++;
 }catch(e){errors.push({file:f.name,error:String(e)})}
 if(count){
 // Reimport restores soft-deleted hierarchy before comparing metadata. Use a fresh
 // server baseline so hidden rows are never mistaken for new records.
 let imported=s;let restored=await remote('/reimport',{series_uids:Array.from(seriesIds)});
 currentState=restored.state;s=structuredClone(currentState);
 for(let k of ['patients','studies','series','instances'])for(let item of imported[k]){
 let included=k==='patients'?imported.studies.some(st=>studyIds.has(st.id)&&st.patient_id===item.id):k==='studies'?studyIds.has(item.id):k==='series'?seriesIds.has(item.id):uids.has(item.id);
 if(included)upsert(s,k,{...item,version:s[k].find(x=>x.id===item.id)?.version});
 }
 await write(s);
 }return {imported:count,skipped:errors}});queue=task.then(()=>undefined,()=>undefined);return task}
export async function exportLocal(fmt,sid){let s=await req('/state'),se=s.series.find(x=>x.id===sid),st=s.studies.find(x=>x.id===se.study_id);s.instances=s.instances.filter(x=>x.series_id===sid).sort((a,b)=>a.order-b.order).map((x,i)=>({...x,slice_index:i}));s.series=[se];s.studies=[st];s.patients=s.patients.filter(x=>x.id===st.patient_id);s.lesions=s.lesions.filter(x=>x.series_id===sid);s.boxes=s.boxes.filter(x=>s.instances.some(i=>i.id===x.sop_instance_uid));s.assessments=s.assessments.filter(x=>x.study_id===st.id&&x.series_id===sid);s.groups=s.groups.filter(x=>s.lesions.some(l=>l.lesion_group_id===x.id));s.segmentations=s.segmentations.filter(x=>x.series_id===sid);delete s.archives;delete s._deleted;s.export_info={scope:'series',series_id:sid,coordinates:'original DICOM pixels; xyxy; zero-based slice_index'};
 if(fmt==='coco'){let cats=Object.fromEntries(s.diseases.map((d,i)=>[d.id,i+1]));return new Blob([JSON.stringify({images:s.instances.map((x,i)=>({id:i+1,file_name:x.id+'.dcm',sop_instance_uid:x.id,width:x.width,height:x.height,slice_index:i,series_id:sid,study_id:st.id,patient_id:st.patient_id})),annotations:s.boxes.map((b,i)=>{let l=s.lesions.find(x=>x.id===b.lesion_instance_id);return {id:i+1,image_id:s.instances.findIndex(x=>x.id===b.sop_instance_uid)+1,category_id:cats[l.disease_type_id],bbox:[b.x_min,b.y_min,b.x_max-b.x_min,b.y_max-b.y_min],area:(b.x_max-b.x_min)*(b.y_max-b.y_min),iscrowd:0,box_id:b.id,lesion_instance_id:l.id,attributes:l.attributes_json,source_box_id:b.source_box_id}}),categories:s.diseases.map(d=>({id:cats[d.id],name:d.disease_name,disease_code:d.id})),study_assessments:s.assessments,lesion_instances:s.lesions,disease_configs:s.diseases,export_info:s.export_info},null,2)],{type:'application/json'})}
 if(fmt==='csv'){let cols=['record_type','patient_id','study_id','series_id','series_description','sop_instance_uid','slice_index','image_width','image_height','disease_type','target_key','lesion_instance_id','box_id','x_min','y_min','x_max','y_max','attributes_json'];let records=s.assessments.map(a=>({...a,record_type:'overall',disease_type:a.disease_type_id}));for(let b of s.boxes){let l=s.lesions.find(x=>x.id===b.lesion_instance_id),im=s.instances.find(x=>x.id===b.sop_instance_uid);records.push({...b,record_type:'box',box_id:b.id,disease_type:l.disease_type_id,slice_index:im.slice_index,image_width:im.width,image_height:im.height,attributes_json:l.attributes_json})}let esc=v=>'"'+String(v??'').replaceAll('"','""')+'"';return new Blob(['\ufeff'+[cols.join(','),...records.map(r=>cols.map(k=>esc(k==='attributes_json'?JSON.stringify(r[k]||{}):({patient_id:st.patient_id,study_id:st.id,series_id:sid,series_description:se.description,...r})[k])).join(','))].join('\r\n')],{type:'text/csv'})}
 return new Blob([JSON.stringify(s,null,2)],{type:'application/json'})}
