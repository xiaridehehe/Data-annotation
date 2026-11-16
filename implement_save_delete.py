from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf-8')
s=s.replace("[status,msg]=S('就绪')", "[status,msg]=S('就绪'),[pending,P]=S(0),[busy,B]=S(false),[archive,A]=S('')")
s=s.replace("async function save(kind,d,record=true){try{", "async function save(kind,d,record=true){P(n=>n+1);try{")
s=s.replace("msg('已保存');return r}catch(e){msg(String(e));throw e}}", "msg('草稿已自动保存，可点击保存标注确认');return r}catch(e){msg(String(e));throw e}finally{P(n=>n-1)}}")
pos=s.index("E(()=>{if(dis?.box_policy")
s=s[:pos]+'''async function commit(){if(pending)throw Error('请等待自动保存完成');let r=await req('/project/save','POST');msg('标注已保存到数据库 · '+new Date(r.saved_at).toLocaleTimeString());return r}
async function removeData(kind,id){
 if(!confirm('删除前请保存标注。点击确定将先保存当前全部标注，再删除所选数据。\\n删除检查或患者会移除其关联标注；删除序列保留检查级整体评价。数据将保留归档，可撤销删除。'))return;
 B(true);try{await commit();let r=await req('/imported/'+kind+'/'+encodeURIComponent(id),'DELETE');A(r.archive_id);series('');slice(0);lesion('');H([]);F([]);vp.current?.element && engine.current?.disableElement('stack');engine.current?.destroy();engine.current=null;vp.current=null;imageMsg('请选择序列');await refresh();msg(r.message)}catch(e){msg('删除未完成：'+String(e))}finally{B(false)}
}
''' +s[pos:]
s=s.replace("<small>{status}</small>","<small>{status}</small><button disabled={pending>0||busy} onClick={async()=>{B(true);try{await commit()}catch(e){msg('保存失败：'+String(e))}finally{B(false)}}>{pending?'正在保存草稿…':'保存标注'}</button>{archive&&<button disabled={busy} onClick={async()=>{B(true);try{await req('/imported/restore/'+archive,'POST');A('');await refresh();msg('已恢复删除的数据')}catch(e){msg(String(e))}finally{B(false)}}}>撤销上次数据删除</button>}")
s=s.replace("<b>{st.patient_id}</b><p>","<b>{st.patient_id}</b><button disabled={pending>0||busy} onClick={()=>removeData('patients',st.patient_id)}>删除此患者全部数据</button><button disabled={pending>0||busy} onClick={()=>removeData('studies',st.id)}>删除此检查</button><p>")
s=s.replace(".map(x=><button className={sid===x.id?", ".map(x=><div key={x.id}><button className={sid===x.id?")
s=s.replace("length} 框</small></button>)", "length} 框</small></button><button disabled={pending>0||busy} onClick={()=>removeData('series',x.id)}>删除此序列</button></div>)")
p.write_text(s,encoding='utf-8')
