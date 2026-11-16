from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf8');pos=s.index('async function copy()')
s=s[:pos]+'''E(()=>{
 function keydown(e:KeyboardEvent){
  let element=e.target as HTMLElement;
  if(element?.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]')||draft||e.isComposing||e.altKey)return;
  let mod=e.ctrlKey||e.metaKey,key=e.key.toLowerCase();
  let run=(action)=>{e.preventDefault();if(e.repeat||pending>0||busy)return;Promise.resolve().then(action).catch(error=>msg('快捷键操作失败：'+String(error)))};
  if(mod&&key==='c'){run(()=>{let box=s.boxes.find(b=>b.sop_instance_uid===im?.id&&b.lesion_instance_id===lid);if(!box){msg('请先选中当前切片的框，再复制');return}selectBox(box);msg('已复制选中框，可切换切片后按 Ctrl+V 粘贴')});return}
  if(mod&&key==='v'){run(()=>{if(!ghost){msg(alreadyHere?'当前切片已有该病灶框':'请先选中或复制一个框，再切换切片粘贴');return}return pasteSelected()});return}
  if(mod&&key==='z'){run(()=>undo(e.shiftKey));return}
  if(mod&&key==='y'){run(()=>undo(true));return}
  if(mod&&key==='s'){run(async()=>{B(true);try{await commit()}finally{B(false)}});return}
  if(mod)return;
  if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();if(images.length)slice(Math.max(0,Math.min(images.length-1,idx+(e.key==='ArrowRight'?1:-1))));return}
  if(e.key==='Escape'){e.preventDefault();CB(null);lesion('');V(null);drag.current=null;mode('select');return}
  if(key==='r'){run(()=>{if(im&&dis?.box_policy!=='NONE')mode('draw')});return}
  if(key==='v'){run(()=>mode('select'));return}
 }
 window.addEventListener('keydown',keydown);return()=>window.removeEventListener('keydown',keydown);
});
''' +s[pos:]
s=s.replace('<button onClick={()=>undo()}>撤销</button>','<button title="Ctrl+Z" onClick={()=>undo()}>撤销</button>')
s=s.replace('<button onClick={()=>undo(true)}>重做</button>','<button title="Ctrl+Y / Ctrl+Shift+Z" onClick={()=>undo(true)}>重做</button>')
s=s.replace('onClick={pasteSelected}>','title="Ctrl+V" onClick={pasteSelected}>')
s=s.replace('<div className="slice-box-toolbar"><b>', '<div className="slice-box-toolbar"><b>')
s=s.replace("{dis?.box_policy!=='NONE'&&<><button disabled={!ghost", "{dis?.box_policy!=='NONE'&&<><button title=\"Ctrl+C\" disabled={!im||!lid||pending>0||busy} onClick={()=>{let box=s.boxes.find(b=>b.sop_instance_uid===im.id&&b.lesion_instance_id===lid);if(box){selectBox(box);msg('已复制选中框')}}}>复制选中框</button><button disabled={!ghost")
s=s.replace('</nav><div className="viewer"', '</nav><div className="shortcut-help">Ctrl+C 复制选中框 · Ctrl+V 粘贴 · Ctrl+Z 撤销 · Ctrl+Y / Ctrl+Shift+Z 重做 · Ctrl+S 保存<br/>← / → 切片 · R 画框 · V 选择 · Esc 取消选择（Mac 使用 ⌘ 代替 Ctrl）</div><div className="viewer"')
p.write_text(s,encoding='utf8')
