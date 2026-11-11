import json, os, uuid, io, csv, zipfile
from pathlib import Path
import numpy as np
import pydicom
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from backend.database import create_database_engine, upsert_sql
from PIL import Image
ROOT=Path(__file__).parent/'data'; ROOT.mkdir(exist_ok=True)
engine=create_database_engine()
def rows(kind):
 with engine.connect() as c: return [json.loads(r[0]) for r in c.execute(text('SELECT data FROM records WHERE kind=:k'),{'k':kind})]
def put(k,d):
 d.setdefault('id',str(uuid.uuid4()))
 with engine.begin() as c: c.execute(upsert_sql(engine),{'k':k,'i':d['id'],'d':json.dumps(d,ensure_ascii=False)})
 return d
def get(k,i):
 return next((d for d in rows(k) if d['id']==i),None)
def field(name,opts='',multi=False): return dict(field_code=name,field_name=name,field_type='multi_select' if multi else ('single_select' if opts else 'text'),options=opts.split('|') if opts else [],required=False)
def disease(code,name,overall,local,policy='OPTIONAL'):
 return dict(id=code,disease_code=code,disease_name=name,overall_fields=overall,lesion_fields=local,box_policy=policy,supports_multi_instance=True,default_assessment_scope='STUDY',active=True)
severity=field('损伤程度','正常|轻度损伤|部分撕裂|完全断裂')
location=field('损伤位置','股骨附着端|韧带中段|胫骨附着端')
morph=field('损伤形态','纤维部分中断|纤维完全中断|韧带增粗|韧带松弛|韧带回缩',True)
def ensure_diseases():
 if rows('diseases'): return
 configs=[disease('ACL_INJURY','ACL 损伤',[field('损伤程度','正常|部分撕裂|完全断裂')],[field('受损束','前内侧束 AM|后外侧束 PL|两束均受损'),location,morph]),disease('PCL_INJURY','PCL 损伤',[severity],[field('受损束','前外侧束 AL|后内侧束 PM|两束均受损'),location,morph])]
 for code,name in [('MCL','MCL'),('LCL','LCL'),('PATELLAR_LIGAMENT','髌韧带'),('PATELLAR_RETINACULUM','髌骨支持带'),('QUADRICEPS_TENDON','股四头肌腱'),('POPLITEUS_TENDON','腘肌腱')]: configs.append(disease(code+'_INJURY',name+'损伤',[severity],[location,morph]))
 configs += [disease('MENISCUS_INJURY','半月板损伤',[field('损伤程度','0级正常|Ⅰ级退变|Ⅱ级退变|Ⅲ级撕裂')],[field('半月板类型','内侧半月板|外侧半月板'),field('撕裂形态','水平撕裂|垂直纵向撕裂|放射状撕裂|桶柄状撕裂|复杂撕裂|根部撕裂|瓣状撕裂',True),field('解剖位置','前角|体部|后角|前根|后根'),field('移位','无移位|移位'),field('突出','无突出|轻度突出|明显突出')]),disease('CARTILAGE_INJURY','软骨损伤',[field('损伤程度','0级正常|1级轻度缺损|2级重度缺损')],[field('缺损形态','软骨变薄|表面不规则|局灶性缺损|多发性缺损|全层缺损',True),field('解剖位置','股骨内侧髁|股骨外侧髁|股骨滑车|胫骨内侧平台|胫骨外侧平台|髌骨关节面')]),disease('HOFFA_FAT_PAD_ABNORMALITY','髌下脂肪垫异常',[field('异常程度','正常|轻度水肿|中度水肿|重度水肿')],[field('异常类型','水肿|挫伤|炎症|纤维化'),field('解剖位置','内侧|外侧|上部|下部'),field('异常形态','局灶性高信号|弥漫性高信号|脂肪垫肿胀|纤维化改变')]),disease('SYNOVIAL_ABNORMALITY','滑膜异常',[field('异常程度','正常|轻度异常|明显异常'),field('异常类型','滑膜增厚|滑膜炎'),field('异常形态','局灶性增厚|弥漫性增厚|滑膜不规则')],[],'NONE'),disease('JOINT_EFFUSION','关节积液',[field('积液程度','无积液|少量积液|中量积液|大量积液'),field('解剖位置','髌上囊|内侧关节隐窝|外侧关节隐窝|髌下关节隐窝|后方关节隐窝',True),field('积液分布','局限性|弥漫性|多区域分布'),field('积液性质','普通积液|积血|积脂|不确定')],[],'NONE')]
 for code,name,types in [('BONE_INJURY','骨骼损伤','骨折|撕脱骨折|骨挫伤'),('SUBCHONDRAL_INJURY','软骨下骨损伤','骨髓水肿|囊性变|软骨下骨折')]:
  fs=[field('损伤类型',types),field('骨骼名称','股骨|胫骨|髌骨|腓骨'),field('解剖位置')]
  fs[2]['options_by']={'field':'骨骼名称','values':{'股骨':['内侧髁','外侧髁','髁间区'],'胫骨':['内侧平台','外侧平台','髁间棘'],'髌骨':['上部','下部','内侧部','外侧部'],'腓骨':['腓骨头','腓骨近端其他区域']}}
  if code=='BONE_INJURY':
   for n,o in [('骨折形态','普通骨折|粉碎性骨折|塌陷性骨折|隐匿性骨折|不适用'),('撕脱','是|否|不适用'),('骨折状态','急性|陈旧性|不适用'),('移位','移位|未移位|不适用')]:
    f=field(n,o);f['hide_when']={'损伤类型':'骨挫伤'};fs.append(f)
  configs.append(disease(code,name,[],fs,'REQUIRED'))
 for d in configs: put('diseases',d)
ensure_diseases()
# Upgrade display labels in existing databases without changing disease IDs.
for code,label,legacy in [
 ('ACL_INJURY','前交叉韧带损伤（ACL）',{'ACL 损伤','ACL损伤'}),
 ('PCL_INJURY','后交叉韧带损伤（PCL）',{'PCL 损伤','PCL损伤'}),
 ('MCL_INJURY','内侧副韧带损伤（MCL）',{'MCL 损伤','MCL损伤'}),
 ('LCL_INJURY','外侧副韧带损伤（LCL）',{'LCL 损伤','LCL损伤'}),
]:
 existing=get('diseases',code)
 if existing and existing.get('disease_name') in legacy:
  existing['disease_name']=label;put('diseases',existing)
app=FastAPI(title='Knee MRI Annotation')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
@app.get('/api/state')
def state():
 ensure_diseases()
 return {k:rows(k) for k in ['patients','studies','series','instances','diseases','assessments','lesions','boxes','groups','segmentations']}
@app.post('/api/import')
async def import_files(files:list[UploadFile]):
 count=0; errors=[]
 for upload in files:
  raw=await upload.read()
  entries=[(upload.filename,raw)]
  if zipfile.is_zipfile(io.BytesIO(raw)):
   with zipfile.ZipFile(io.BytesIO(raw)) as z: entries=[(n,z.read(n)) for n in z.namelist() if not n.endswith('/')]
  for name,data in entries:
   try:
    ds=pydicom.dcmread(io.BytesIO(data)); uid=str(ds.SOPInstanceUID)
    if not hasattr(ds,'PixelData'): continue
    path=ROOT/(str(uuid.uuid4())+'.dcm');path.write_bytes(data)
    patient=str(getattr(ds,'PatientID','UNKNOWN'));study=str(ds.StudyInstanceUID);series=str(ds.SeriesInstanceUID)
    put('patients',{'id':patient});put('studies',{'id':study,'patient_id':patient,'description':str(getattr(ds,'StudyDescription','')),'date':str(getattr(ds,'StudyDate',''))})
    orient=list(map(float,getattr(ds,'ImageOrientationPatient',[])));pos=list(map(float,getattr(ds,'ImagePositionPatient',[])))
    axis='未知';order=float(getattr(ds,'InstanceNumber',0))
    if len(orient)==6 and len(pos)==3:
     normal=np.cross(orient[:3],orient[3:]);order=float(np.dot(normal,pos));axis=['SAG','COR','AX'][int(np.argmax(abs(normal)))]
    put('series',{'id':series,'study_id':study,'description':str(getattr(ds,'SeriesDescription',getattr(ds,'ProtocolName','未命名序列'))),'number':str(getattr(ds,'SeriesNumber','')),'orientation':axis})
    meta={k:str(getattr(ds,k,'')) for k in ['Modality','PixelSpacing','SliceThickness','SpacingBetweenSlices','WindowCenter','WindowWidth','MagneticFieldStrength','RepetitionTime','EchoTime','Laterality','ProtocolName']}
    put('instances',{'id':uid,'series_id':series,'path':str(path),'order':order,'width':int(ds.Columns),'height':int(ds.Rows),'position':pos,'orientation':orient,'metadata':meta});count+=1
   except Exception as e: errors.append({'file':name,'error':str(e)})
 return {'imported':count,'skipped':errors}
@app.get('/api/dicom/{uid}')
def dicom(uid:str):
 d=get('instances',uid)
 if not d: raise HTTPException(404)
 return FileResponse(d['path'],media_type='application/dicom')
@app.put('/api/{kind}')
def save(kind:str,d:dict):
 if kind not in ['diseases','assessments','lesions','boxes','groups','segmentations']: raise HTTPException(400)
 if kind=='assessments': d['id']=':'.join([d['study_id'],d['disease_type_id'],d['target_key']])
 if kind=='boxes':
  lesion=get('lesions',d['lesion_instance_id']);image=get('instances',d['sop_instance_uid'])
  if not lesion or not image or lesion['series_id']!=image['series_id']: raise HTTPException(422,'序列不匹配')
  if not (0<=d['x_min']<d['x_max']<=image['width'] and 0<=d['y_min']<d['y_max']<=image['height']): raise HTTPException(422,'框坐标越界')
  existing=next((b for b in rows('boxes') if b['lesion_instance_id']==lesion['id'] and b['sop_instance_uid']==image['id']),None)
  if existing:d['id']=existing['id']
 if kind=='lesions':
  existing=get('lesions',d.get('id',''))
  if existing and existing.get('color'):d['color']=existing['color']
  elif not d.get('color'):
   used={l.get('color') for l in rows('lesions')}
   color='#'+uuid.uuid4().hex[:6]
   while color in used:color='#'+uuid.uuid4().hex[:6]
   d['color']=color
  dis=get('diseases',d['disease_type_id'])
  if not dis or dis['box_policy']=='NONE':raise HTTPException(422,'该病害不支持病灶框')
 return put(kind,d)
@app.delete('/api/{kind}/{id}')
def delete(kind:str,id:str):
 if kind not in ['boxes','lesions','assessments']:raise HTTPException(400)
 with engine.begin() as c:
  if kind=='lesions':
   for b in rows('boxes'):
    if b['lesion_instance_id']==id:c.execute(text('DELETE FROM records WHERE id=:id'),{'id':b['id']})
  c.execute(text('DELETE FROM records WHERE kind=:k AND id=:id'),{'k':kind,'id':id})
 return {'ok':True}
@app.get('/api/export/{fmt}')
def export(fmt:str,series_id:str | None = None):
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
     if config['id'] in {'ACL_INJURY','PCL_INJURY','MCL_INJURY','LCL_INJURY','MENISCUS_INJURY','CARTILAGE_INJURY','PATELLAR_LIGAMENT_INJURY','PATELLAR_RETINACULUM_INJURY','QUADRICEPS_TENDON_INJURY','POPLITEUS_TENDON_INJURY','HOFFA_FAT_PAD_ABNORMALITY','SYNOVIAL_ABNORMALITY','JOINT_EFFUSION','BONE_INJURY','SUBCHONDRAL_INJURY'} or f.get('required'):
      if values.get(f['field_code']) in [None,'',[]]:errors.append({'record_id':record['id'],'field':f['field_name']})
  for l in s['lesions']:
   config=get('diseases',l['disease_type_id'])
   if config['overall_fields'] and not any(a['disease_type_id']==config['id'] for a in s['assessments']):errors.append({'record_id':l['id'],'field':'整体评价'})
  if errors:raise HTTPException(422,{'message':'标注尚未完成','incomplete_items':errors})
  for index,i in enumerate(s['instances']):i['slice_index']=index
 s['export_info']={'scope':'series' if series_id else 'all','series_id':series_id,'coordinates':'original DICOM pixels; xyxy; zero-based slice_index'}
 for i in s['instances']:i.pop('path',None)
 if fmt=='json':return Response(json.dumps(s,ensure_ascii=False,indent=2),media_type='application/json')
 if fmt=='coco':
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
 return Response('\ufeff'+out.getvalue(),media_type='text/csv')

# Explicit save creates an immutable database snapshot of the committed annotations.
@app.post('/api/project/save')
def save_project(details:dict | None = None):
 from datetime import datetime, timezone
 snapshot=state()
 record={'id':str(uuid.uuid4()),'saved_at':datetime.now(timezone.utc).isoformat(),'state':snapshot,'validation':details or {'assessment_status':'DRAFT'}}
 put('snapshots',record)
 return {'id':record['id'],'saved_at':record['saved_at'],'message':'标注结果已保存到数据库'}

@app.delete('/api/imported/{kind}/{item_id}')
def remove_imported(kind:str,item_id:str):
 if kind not in ['patients','studies','series']:raise HTTPException(400,'不支持的删除范围')
 if not get(kind,item_id):raise HTTPException(404,'数据不存在')
 snapshot=state()
 study_ids={x['id'] for x in snapshot['studies'] if (kind=='patients' and x['patient_id']==item_id) or (kind=='studies' and x['id']==item_id)}
 series_ids={x['id'] for x in snapshot['series'] if x['study_id'] in study_ids or (kind=='series' and x['id']==item_id)}
 instances={x['id'] for x in snapshot['instances'] if x['series_id'] in series_ids}
 lesions={x['id'] for x in snapshot['lesions'] if x['series_id'] in series_ids}
 affected={'studies':study_ids,'series':series_ids,'instances':instances,'lesions':lesions}
 affected['boxes']={x['id'] for x in snapshot['boxes'] if x['lesion_instance_id'] in lesions or x['sop_instance_uid'] in instances}
 affected['assessments']={x['id'] for x in snapshot['assessments'] if x['study_id'] in study_ids}
 affected['groups']={x['id'] for x in snapshot['groups'] if x.get('study_id') in study_ids}
 affected['segmentations']={x['id'] for x in snapshot['segmentations'] if x.get('study_id') in study_ids or x.get('series_id') in series_ids}
 if kind=='patients':affected['patients']={item_id}
 from datetime import datetime,timezone
 archive={'id':str(uuid.uuid4()),'saved_at':datetime.now(timezone.utc).isoformat(),'scope':{'kind':kind,'id':item_id},'records':{k:[x for x in snapshot[k] if x['id'] in ids] for k,ids in affected.items()}}
 # Archive and remove references atomically; original files remain recoverable.
 with engine.begin() as c:
  c.execute(text('INSERT INTO records VALUES (:k,:i,:d)'),{'k':'deleted_imports','i':archive['id'],'d':json.dumps(archive,ensure_ascii=False)})
  for k,ids in affected.items():
   for item in ids:c.execute(text('DELETE FROM records WHERE kind=:k AND id=:i'),{'k':k,'i':item})
 return {'ok':True,'archive_id':archive['id'],'message':'已从列表移除，原始影像和标注保留在数据库归档中'}

@app.post('/api/imported/restore/{archive_id}')
def restore_imported(archive_id:str):
 archive=get('deleted_imports',archive_id)
 if not archive:raise HTTPException(404)
 with engine.begin() as c:
  for k,items in archive['records'].items():
   for item in items:
    existing=c.execute(text('SELECT id FROM records WHERE id=:i'),{'i':item['id']}).first()
    if not existing:c.execute(text('INSERT INTO records VALUES (:k,:i,:d)'),{'k':k,'i':item['id'],'d':json.dumps(item,ensure_ascii=False)})
  c.execute(text('DELETE FROM records WHERE kind=:k AND id=:i'),{'k':'deleted_imports','i':archive_id})
 return {'ok':True}

@app.delete('/api/slices/{uid}/boxes')
def clear_slice_boxes(uid:str):
 if not get('instances',uid):raise HTTPException(404,'切片不存在')
 boxes=[b for b in rows('boxes') if b['sop_instance_uid']==uid]
 with engine.begin() as c:
  for box in boxes:c.execute(text('DELETE FROM records WHERE kind=:k AND id=:i'),{'k':'boxes','i':box['id']})
 return {'deleted':boxes,'count':len(boxes)}
