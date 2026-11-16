from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf8')
s=s.replace("let el=R<HTMLDivElement>(null)","let reminded=R(new Set<string>());let el=R<HTMLDivElement>(null)")
pos=s.index('async function commit()')
s=s[:pos]+'''const builtinCodes=new Set(['ACL_INJURY','PCL_INJURY','MCL_INJURY','LCL_INJURY','PATELLAR_LIGAMENT_INJURY','PATELLAR_RETINACULUM_INJURY','QUADRICEPS_TENDON_INJURY','POPLITEUS_TENDON_INJURY','MENISCUS_INJURY','CARTILAGE_INJURY','HOFFA_FAT_PAD_ABNORMALITY','SYNOVIAL_ABNORMALITY','JOINT_EFFUSION','BONE_INJURY','SUBCHONDRAL_INJURY']);
function applicable(fields,values){return (fields||[]).filter(f=>!f.hide_when||!Object.entries(f.hide_when).some(([k,v])=>values[k]===v))}
function empty(value){return value===undefined||value===null||value===''||(Array.isArray(value)&&!value.filter(x=>x!=='').length)}
function missing(config,fields,values){return applicable(fields,values).filter(f=>(builtinCodes.has(config.id)||f.required)&&empty(values[f.field_code])).map(f=>f.field_name)}
function progress(config,fields,values){let fs=applicable(fields,values).filter(f=>builtinCodes.has(config.id)||f.required),miss=missing(config,fields,values);return <div className={'completion '+(miss.length?'incomplete':'complete')} role="status">{miss.length?`待填写 ${fs.length-miss.length}/${fs.length} · 缺少：${miss.join('、')}`:'适用必填属性已填写完整'}</div>}
function allowLeave(){if(!selected||!dis)return true;let miss=missing(dis,dis.lesion_fields,selected.attributes_json||{});if(!miss.length)return true;let signature=selected.id+':'+[...miss].sort().join('|');if(reminded.current.has(signature))return true;if(!confirm('当前病灶仍缺：'+miss.join('、')+'。\\n确定：保留草稿并切换；取消：继续填写。'))return false;reminded.current.add(signature);return true}
function issues(scope){let result=[];let started=s.assessments.filter(a=>!scope||a.study_id===scope);for(let a of started){let d=s.diseases.find(d=>d.id===a.disease_type_id);if(!d)continue;let miss=missing(d,d.overall_fields,a.attributes_json||{});if(miss.length)result.push({study_id:a.study_id,disease:d.id,target:a.target_key,label:d.disease_name+' 整体评价（'+a.target_key+'）',missing:miss})}
 for(let l of s.lesions.filter(l=>!scope||l.study_id===scope)){let d=s.diseases.find(d=>d.id===l.disease_type_id);if(!d)continue;let miss=missing(d,d.lesion_fields,l.attributes_json||{});if(miss.length)result.push({study_id:l.study_id,disease:d.id,lesion:l.id,series:l.series_id,label:d.disease_name+' 病灶 '+l.id.slice(0,8),missing:miss});if(d.overall_fields.length&&!started.some(a=>a.study_id===l.study_id&&a.disease_type_id===d.id)){result.push({study_id:l.study_id,disease:d.id,series:l.series_id,label:d.disease_name+' 整体评价',missing:['尚未填写整体评价']})}}
 return result}
let currentIssues=issues(study);
function checkSummary(scope,action){let list=issues(scope);return !list.length||confirm(action+'前检查：共 '+list.length+' 项未完成。\\n'+list.slice(0,12).map(x=>x.label+'：'+x.missing.join('、')).join('\\n')+'\\n\\n确定：'+(action==='保存'?'保存为未完成草稿':'导出草稿')+'；取消：返回补填。')}
function locateIssue(issue){if(!allowLeave())return;let targetSeries=issue.series||s.series.find(x=>x.study_id===issue.study_id)?.id;if(targetSeries!==sid){series(targetSeries);slice(0)}disease(issue.disease);if(issue.target&&issue.disease==='MENISCUS_INJURY')T(issue.target);if(issue.lesion){let box=s.boxes.find(b=>b.lesion_instance_id===issue.lesion);if(box){let imgs=s.instances.filter(x=>x.series_id===targetSeries).sort((a,b)=>a.order-b.order);slice(Math.max(0,imgs.findIndex(x=>x.id===box.sop_instance_uid)));setTimeout(()=>selectBox(box),0)}}}
''' +s[pos:]
s=s.replace("let r=await req('/project/save','POST');", "if(!checkSummary(undefined,'保存'))throw Error('已取消保存，请补填属性');let r=await req('/project/save','POST',{assessment_status:issues(undefined).length?'DRAFT':'COMPLETE',incomplete_items:issues(undefined)});")
s=s.replace("msg('标注已保存到数据库 · '","msg((issues(undefined).length?'未完成草稿已保存到数据库 · ':'标注已保存到数据库 · ')")
s=s.replace("function selectBox(b){let l=", "function selectBox(b){if(b.lesion_instance_id!==lid&&!allowLeave())return;let l=")
s=s.replace("onChange={e=>disease(e.target.value)}", "onChange={e=>{if(allowLeave())disease(e.target.value)}}")
s=s.replace("onClick={()=>{series(x.id);slice(0)}}", "onClick={()=>{if(allowLeave()){series(x.id);slice(0)}}}")
s=s.replace("<h3>整体评价 · 当前检查</h3>{forms", "<h3>整体评价 · 当前检查</h3>{progress(dis,dis.overall_fields,ass?.attributes_json||{})}{forms")
s=s.replace("<h3>局部病灶属性</h3>{forms", "<h3>局部病灶属性</h3>{progress(dis,dis.lesion_fields,selected.attributes_json||{})}{forms")
s=s.replace("<label key={f.field_code}>", "<label className={empty(values[f.field_code])&&(builtinCodes.has(dis?.id)||f.required)?'missing-field':''} key={f.field_code}>")
s=s.replace("target=\"_blank\">导出", "target=\"_blank\" onClick={e=>{if(pending||busy||!checkSummary(undefined,'导出'))e.preventDefault()}}>导出")
s=s.replace('<h3>统一病害标注</h3>', '''<h3>统一病害标注</h3>{study&&currentIssues.length>0&&<details className="issue-summary"><summary>当前检查有 {currentIssues.length} 项未完成（点击查看）</summary>{currentIssues.map((item,i)=><button key={i} onClick={()=>locateIssue(item)}>{item.label}：{item.missing.join('、')}</button>)}</details>}''')
p.write_text(s,encoding='utf8')
p=Path('backend/main.py');s=p.read_text(encoding='utf8').replace('def save_project():','def save_project(details:dict | None = None):').replace("'state':snapshot}","'state':snapshot,'validation':details or {'assessment_status':'DRAFT'}}")
p.write_text(s,encoding='utf8')
