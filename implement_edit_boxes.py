from pathlib import Path
p=Path('frontend/main.tsx');s=p.read_text(encoding='utf8')
start=s.index('function rectangle(');end=s.index('function forms(',start)
s=s[:start]+'''function lesionColor(id){let l=s.lesions.find(x=>x.id===id);if(l?.color)return l.color;let hash=2166136261;for(let ch of id||'')hash=Math.imul(hash^ch.charCodeAt(0),16777619);return `hsl(${(hash>>>0)%360},85%,65%)`}
function rectangle(b,key,color){let a=projected(b.x_min,b.y_min),z=projected(b.x_max,b.y_max);if(!a||!z)return null;let active=b.lesion_instance_id===lid;let x=Math.min(a[0],z[0]),y=Math.min(a[1],z[1]),w=Math.abs(z[0]-a[0]),h=Math.abs(z[1]-a[1]);return <g key={key}><rect x={x} y={y} width={w} height={h} fill={active?color:'none'} fillOpacity={active?0.12:0} stroke={color} strokeWidth={active?3:2}/>{active&&[[x,y],[x+w,y],[x,y+h],[x+w,y+h]].map(([cx,cy],i)=><rect key={i} x={cx-4} y={cy-4} width="8" height="8" fill={color} stroke="white"/>)}<text x={x} y={y-5} fill={color} fontSize="13">{key==='preview'?'绘制中':b.lesion_instance_id?.slice(0,8)}</text></g>}
function startPointer(e){if(!im||!vp.current?.getImageData())return;e.currentTarget.setPointerCapture(e.pointerId);let p=point(e);
 if(tool==='select'){
  let current=s.boxes.filter(b=>b.sop_instance_uid===im.id).sort((a,b)=>Number(b.lesion_instance_id===lid)-Number(a.lesion_instance_id===lid));
  let rect=el.current.getBoundingClientRect(),screen=[e.clientX-rect.left,e.clientY-rect.top];
  for(let b of current){for(let corner of [['x_min','y_min'],['x_max','y_min'],['x_min','y_max'],['x_max','y_max']]){let q=projected(b[corner[0]],b[corner[1]]);if(q&&Math.hypot(q[0]-screen[0],q[1]-screen[1])<12){selectBox(b);drag.current={edit:b,corner,p};V({...b});return}}}
  for(let b of current){if(p[0]>=b.x_min&&p[0]<=b.x_max&&p[1]>=b.y_min&&p[1]<=b.y_max){selectBox(b);drag.current={edit:b,p};V({...b});return}}
  lesion('');return;
 }
 if(tool==='draw'&&dis?.box_policy==='NONE')return;
 drag.current={p,x:e.clientX,y:e.clientY,camera:vp.current.getCamera(),props:vp.current.getProperties()};
}
function selectBox(b){let l=s.lesions.find(x=>x.id===b.lesion_instance_id);if(l){disease(l.disease_type_id);lesion(l.id)}}
function editedBox(d,p){let b={...d.edit};if(d.corner){b[d.corner[0]]=p[0];b[d.corner[1]]=p[1];let x=Math.min(b.x_min,b.x_max),y=Math.min(b.y_min,b.y_max);b.x_max=Math.max(b.x_min,b.x_max);b.y_max=Math.max(b.y_min,b.y_max);b.x_min=x;b.y_min=y}else{let dx=Math.max(-b.x_min,Math.min(im.width-b.x_max,p[0]-d.p[0])),dy=Math.max(-b.y_min,Math.min(im.height-b.y_max,p[1]-d.p[1]));b.x_min+=dx;b.x_max+=dx;b.y_min+=dy;b.y_max+=dy}return b}
''' +s[end:]
s=s.replace("V(null);if(tool!=='draw')return;let p=point(e);", "V(null);if(a.edit){let b=editedBox(a,point(e));if(b.x_max-b.x_min>=1&&b.y_max-b.y_min>=1)await save('boxes',b);return}if(tool!=='draw')return;let p=point(e);")
a=s.index('onPointerDown={e=>{');b=s.index(' onPointerMove=',a)
s=s[:a]+'onPointerDown={startPointer}'+s[b:]
s=s.replace("let d=drag.current;if(!d)return;if(tool==='draw')", "let d=drag.current;if(!d)return;if(d.edit){V(editedBox(d,point(e)));return}if(tool==='draw')")
s=s.replace(".map(b=>rectangle(b,b.id,b.lesion_instance_id===lid?'#ffe066':'#42e3b4'))", ".filter(b=>!preview?.id||b.id!==preview.id).map(b=>rectangle(b,b.id,lesionColor(b.lesion_instance_id)))")
s=s.replace("preview&&rectangle(preview,'preview','#ffe066')", "preview&&rectangle(preview,preview.id||'preview',preview.lesion_instance_id?lesionColor(preview.lesion_instance_id):'#ffe066')")
s=s.replace("lesion('')},[di,sid]);", "},[di,sid]);\nE(()=>{lesion('');V(null)},[sid]);")
s=s.replace("<button className={lid===l.id?'active':''} onClick", "<button style={{borderLeft:'5px solid '+lesionColor(l.id)}} className={lid===l.id?'active':''} onClick")
p.write_text(s,encoding='utf8')
p=Path('backend/main.py');s=p.read_text(encoding='utf8');needle=" if kind=='lesions':\n  dis=";s=s.replace(needle," if kind=='lesions':\n  existing=get('lesions',d.get('id',''))\n  if existing and existing.get('color'):d['color']=existing['color']\n  elif not d.get('color'):\n   used={l.get('color') for l in rows('lesions')}\n   color='#'+uuid.uuid4().hex[:6]\n   while color in used:color='#'+uuid.uuid4().hex[:6]\n   d['color']=color\n  dis=")
p.write_text(s,encoding='utf8')
