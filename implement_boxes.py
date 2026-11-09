from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf8')
s=s.replace("[archive,A]=S('')", "[archive,A]=S(''),[preview,V]=S<any>(null),[renderVersion,RV]=S(0)")
pos=s.index('function forms(')
s=s[:pos]+'''E(()=>{let element=el.current;if(!element)return;let redraw=()=>RV(n=>n+1);element.addEventListener(Enums.Events.IMAGE_RENDERED,redraw);return()=>element.removeEventListener(Enums.Events.IMAGE_RENDERED,redraw)},[]);
function projected(x,y){try{let data=vp.current?.getImageData()?.imageData;if(!data)return null;return vp.current.worldToCanvas(data.indexToWorld([x,y,0]))}catch{return null}}
function rectangle(b,key,color){let a=projected(b.x_min,b.y_min),z=projected(b.x_max,b.y_max);if(!a||!z)return null;return <g key={key}><rect x={Math.min(a[0],z[0])} y={Math.min(a[1],z[1])} width={Math.abs(z[0]-a[0])} height={Math.abs(z[1]-a[1])} fill="none" stroke={color} strokeWidth="2"/><text x={Math.min(a[0],z[0])} y={Math.min(a[1],z[1])-5} fill={color} fontSize="13">{key==='preview'?'绘制中':b.lesion_instance_id?.slice(0,8)}</text></g>}
''' +s[pos:]
s=s.replace("let a=drag.current;drag.current=null;if(tool!=='draw')return;", "let a=drag.current;drag.current=null;V(null);if(tool!=='draw')return;")
s=s.replace("['select','window','pan','zoom'].map(t=><button", "['select','draw','window','pan','zoom'].map(t=><button disabled={t==='draw'&&(!im||dis?.box_policy==='NONE')}")
s=s.replace("select:'选择',window:", "select:'选择',draw:'矩形框标注',window:")
s=s.replace("let d=drag.current;if(!d||tool==='draw'||tool==='select')return;", "let d=drag.current;if(!d)return;if(tool==='draw'){let p=point(e);V({x_min:Math.min(d.p[0],p[0]),y_min:Math.min(d.p[1],p[1]),x_max:Math.max(d.p[0],p[0]),y_max:Math.max(d.p[1],p[1])});return}if(tool==='select')return;")
s=s.replace("<div className=\"viewer\" ref={el}", "<div className=\"viewer\" style={{cursor:tool==='draw'?'crosshair':'default'}} ref={el}")
s=s.replace(">{!im&&<div className=\"empty\">", "><svg style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none',zIndex:5}}>{s.boxes.filter(b=>b.sop_instance_uid===im?.id).map(b=>rectangle(b,b.id,b.lesion_instance_id===lid?'#ffe066':'#42e3b4'))}{preview&&rectangle(preview,'preview','#ffe066')}</svg>{!im&&<div className=\"empty\">")
s=s.replace("if(!im||!vp.current?.getImageData())return;", "if(!im||!vp.current?.getImageData())return;if(tool==='draw'&&dis?.box_policy==='NONE')return;")
s=s.replace("mode('draw');lesion('')", "mode('draw');lesion('');imageMsg('矩形框标注：在影像上按住左键拖动，松开完成。')")
p.write_text(s,encoding='utf8')
