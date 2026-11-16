from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf8')
s=s.replace("[preview,V]=S<any>(null)","[preview,V]=S<any>(null),[clipboard,CB]=S<any>(null)")
s=s.replace("E(()=>{lesion('');V(null)},[sid]);", "E(()=>{lesion('');V(null);CB(null)},[sid]);\nE(()=>{V(null);drag.current=null},[idx]);")
s=s.replace("let active=b.lesion_instance_id===lid;", "let active=b.lesion_instance_id===lid&&!b.ghost;")
s=s.replace('<g key={key}><rect', '<g key={key} opacity={b.ghost?0.5:1}><rect')
s=s.replace('strokeWidth={active?3:2}', 'strokeWidth={active?3:2} strokeDasharray={b.ghost?\'6 4\':undefined}')
s=s.replace("{key==='preview'?'绘制中':b.lesion_instance_id?.slice(0,8)}", "{b.ghost?'待粘贴 · '+b.lesion_instance_id?.slice(0,8):key==='preview'?'绘制中':b.lesion_instance_id?.slice(0,8)}")
s=s.replace("disease(l.disease_type_id);lesion(l.id)", "disease(l.disease_type_id);lesion(l.id);CB({...b,series_id:l.series_id})")
s=s.replace("lesion(l.id);mode('select')", "lesion(l.id);mode('select');CB({...s.boxes.find(b=>b.lesion_instance_id===l.id&&b.sop_instance_uid===im.id),lesion_instance_id:l.id,series_id:sid,sop_instance_uid:im.id})")
# Store the actual saved box for a newly drawn lesion.
s=s.replace("await save('boxes',{lesion_instance_id:l.id", "let createdBox=await save('boxes',{lesion_instance_id:l.id")
s=s.replace("CB({...s.boxes.find(b=>b.lesion_instance_id===l.id&&b.sop_instance_uid===im.id),lesion_instance_id:l.id,series_id:sid,sop_instance_uid:im.id})", "CB({...createdBox,series_id:sid})")
pos=s.index('async function copy()')
s=s[:pos]+'''let source=clipboard&&clipboard.series_id===sid&&clipboard.lesion_instance_id===lid&&s.lesions.some(l=>l.id===lid)?(s.boxes.find(b=>b.id===clipboard.id)||clipboard):null;
let alreadyHere=source&&s.boxes.some(b=>b.lesion_instance_id===source.lesion_instance_id&&b.sop_instance_uid===im?.id);
let ghost=source&&im&&source.sop_instance_uid!==im.id&&!alreadyHere?{...source,ghost:true}:null;
async function pasteSelected(){if(!ghost||pending||busy)return;B(true);try{let {series_id,ghost:unused,...box}=ghost;await save('boxes',{...box,id:crypto.randomUUID(),sop_instance_uid:im.id,slice_index:idx,source_box_id:source.id});msg('已粘贴：保留原病灶实例、颜色和属性')}catch(e){msg('粘贴失败：'+String(e))}finally{B(false)}}
''' +s[pos:]
s=s.replace("{preview&&rectangle(preview", "{ghost&&rectangle(ghost,'ghost',lesionColor(ghost.lesion_instance_id))}{preview&&rectangle(preview")
a=s.index("{dis?.box_policy!=='NONE'&&<button disabled={!im||idx===0")
b=s.index('</button>}',a)+len('</button>}')
s=s[:a]+'''{dis?.box_policy!=='NONE'&&<><button disabled={!ghost||pending>0||busy} onClick={pasteSelected}>{alreadyHere?'当前切片已有该病灶框':'粘贴选中框到当前切片'}</button><button disabled={!source} onClick={()=>{CB(null);lesion('')}}>取消选中</button>{ghost&&<small>虚线仅为预览，点击粘贴后保存为实线框。</small>}</>}'''+s[b:]
p.write_text(s,encoding='utf8')
