from pathlib import Path
p=Path('backend/main.py');s=p.read_text(encoding='utf8')
s=s.replace('def export(fmt:str):\n s=state()', '''def export(fmt:str,series_id:str | None = None):
 s=state()
 if fmt not in ['json','csv','coco']:raise HTTPException(400,'不支持的导出格式')
 if series_id:
  series=get('series',series_id)
  if not series:raise HTTPException(404,'序列不存在')
  study=get('studies',series['study_id'])
  s['patients']=[p for p in s['patients'] if p['id']==study['patient_id']]
  s['studies']=[study];s['series']=[series]
  s['instances']=sorted([i for i in s['instances'] if i['series_id']==series_id],key=lambda i:i['order'])
  s['lesions']=[l for l in s['lesions'] if l['series_id']==series_id]
  ids={l['id'] for l in s['lesions']};uids={i['id'] for i in s['instances']}
  s['boxes']=[b for b in s['boxes'] if b['lesion_instance_id'] in ids and b['sop_instance_uid'] in uids]
  s['assessments']=[a for a in s['assessments'] if a['study_id']==study['id']]
  s['groups']=[g for g in s['groups'] if g['id'] in {l.get('lesion_group_id') for l in s['lesions']}]
  s['segmentations']=[r for r in s['segmentations'] if r.get('series_id')==series_id]
  errors=[]
  for kind,fields in [('assessments','overall_fields'),('lesions','lesion_fields')]:
   for record in s[kind]:
    config=get('diseases',record['disease_type_id']);values=record.get('attributes_json',{})
    for f in config[fields]:
     if f.get('hide_when') and any(values.get(k)==v for k,v in f['hide_when'].items()):continue
     if config.get('default_assessment_scope')=='STUDY' or f.get('required'):
      if values.get(f['field_code']) in [None,'',[]]:errors.append({'record_id':record['id'],'field':f['field_name']})
  for l in s['lesions']:
   config=get('diseases',l['disease_type_id'])
   if config['overall_fields'] and not any(a['disease_type_id']==config['id'] for a in s['assessments']):errors.append({'record_id':l['id'],'field':'整体评价'})
  if errors:raise HTTPException(422,{'message':'标注尚未完成','incomplete_items':errors})
  for index,i in enumerate(s['instances']):i['slice_index']=index
 s['export_info']={'scope':'series' if series_id else 'all','series_id':series_id,'coordinates':'original DICOM pixels; xyxy; zero-based slice_index'}''')
a=s.index(" if fmt=='coco':",s.index('def export('));b=s.index(" return Response('\\ufeff'+out.getvalue(),media_type='text/csv')",a)+len(" return Response('\\ufeff'+out.getvalue(),media_type='text/csv')")
s=s[:a]+''' if fmt=='coco':
  cats={d['id']:n+1 for n,d in enumerate(s['diseases'])};image_ids={i['id']:n+1 for n,i in enumerate(s['instances'])};anns=[]
  for n,b in enumerate(s['boxes']):
   l=get('lesions',b['lesion_instance_id']);w=b['x_max']-b['x_min'];h=b['y_max']-b['y_min']
   anns.append({'id':n+1,'image_id':image_ids[b['sop_instance_uid']],'category_id':cats[l['disease_type_id']],'bbox':[b['x_min'],b['y_min'],w,h],'area':w*h,'iscrowd':0,'box_id':b['id'],'lesion_instance_id':l['id'],'attributes':l.get('attributes_json',{}),'source_box_id':b.get('source_box_id')})
  images=[]
  for i in s['instances']:
   se=get('series',i['series_id']);st=get('studies',se['study_id'])
   images.append({'id':image_ids[i['id']],'file_name':i['id']+'.dcm','width':i['width'],'height':i['height'],'sop_instance_uid':i['id'],'slice_index':i.get('slice_index'),'series_id':se['id'],'series_description':se['description'],'study_id':st['id'],'patient_id':st['patient_id']})
  return {'images':images,'annotations':anns,'categories':[{'id':cats[d['id']],'name':d['disease_name'],'disease_code':d['id']} for d in s['diseases']],'study_assessments':s['assessments'],'lesion_instances':s['lesions'],'disease_configs':s['diseases'],'export_info':s['export_info']}
 out=io.StringIO();writer=csv.writer(out)
 columns=['record_type','patient_id','study_id','series_id','series_description','sop_instance_uid','slice_index','image_width','image_height','disease_type','target_key','lesion_instance_id','box_id','x_min','y_min','x_max','y_max','attributes_json']
 writer.writerow(columns)
 def write(row):writer.writerow([row.get(k,'') for k in columns])
 for a in s['assessments']:
  st=get('studies',a['study_id']);se=s['series'][0] if series_id else {}
  write(dict(record_type='overall',patient_id=st['patient_id'],study_id=st['id'],series_id=se.get('id',''),series_description=se.get('description',''),disease_type=a['disease_type_id'],target_key=a['target_key'],attributes_json=json.dumps(a.get('attributes_json',{}),ensure_ascii=False)))
 for b in s['boxes']:
  l=get('lesions',b['lesion_instance_id']);se=get('series',l['series_id']);st=get('studies',l['study_id']);i=next(x for x in s['instances'] if x['id']==b['sop_instance_uid'])
  write(dict(b,record_type='box',patient_id=st['patient_id'],study_id=st['id'],series_id=se['id'],series_description=se['description'],slice_index=i.get('slice_index',b.get('slice_index')),box_id=b['id'],disease_type=l['disease_type_id'],attributes_json=json.dumps(l.get('attributes_json',{}),ensure_ascii=False)))
 return Response('\\ufeff'+out.getvalue(),media_type='text/csv')''' +s[b:]
p.write_text(s,encoding='utf8')
