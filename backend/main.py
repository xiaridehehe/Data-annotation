import json, os, uuid, io, csv, zipfile
from pathlib import Path
import numpy as np
import pydicom
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from PIL import Image
ROOT=Path(__file__).parent/'data'; ROOT.mkdir(exist_ok=True)
engine=create_engine('sqlite:///'+str(ROOT/'annotations.db'))
with engine.begin() as c:
 c.execute(text('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT PRIMARY KEY, data TEXT NOT NULL)'))
def rows(kind):
 with engine.connect() as c: return [json.loads(r[0]) for r in c.execute(text('SELECT data FROM records WHERE kind=:k'),{'k':kind})]
def put(k,d):
 d.setdefault('id',str(uuid.uuid4()))
 with engine.begin() as c: c.execute(text('INSERT OR REPLACE INTO records VALUES (:k,:i,:d)'),{'k':k,'i':d['id'],'d':json.dumps(d,ensure_ascii=False)})
 return d
def get(k,i):
 return next((d for d in rows(k) if d['id']==i),None)
def field(name,opts='',multi=False): return dict(field_code=name,field_name=name,field_type='multi_select' if multi else ('single_select' if opts else 'text'),options=opts.split('|') if opts else [],required=False)
def disease(code,name,overall,local,policy='OPTIONAL'):
 return dict(id=code,disease_code=code,disease_name=name,overall_fields=overall,lesion_fields=local,box_policy=policy,supports_multi_instance=True,default_assessment_scope='STUDY',active=True)
severity=field('损伤程度','正常|轻度损伤|部分撕裂|完全断裂')
location=field('损伤位置','股骨附着端|韧带中段|胫骨附着端')
morph=field('损伤形态','纤维部分中断|纤维完全中断|韧带增粗|韧带松弛|韧带回缩',True)
if not rows('diseases'):
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
app=FastAPI(title='Knee MRI Annotation')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
@app.get('/api/state')
def state(): return {k:rows(k) for k in ['patients','studies','series','instances','diseases','assessments','lesions','boxes','groups','segmentations']}
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
def export(fmt:str):
 s=state()
 for i in s['instances']:i.pop('path',None)
 if fmt=='json':return Response(json.dumps(s,ensure_ascii=False,indent=2),media_type='application/json')
 if fmt=='coco':
  images=[{'id':i['id'],'file_name':i['id']+'.dcm','width':i['width'],'height':i['height']} for i in s['instances']];anns=[]
  for b in s['boxes']:
   l=get('lesions',b['lesion_instance_id']);w=b['x_max']-b['x_min'];h=b['y_max']-b['y_min'];anns.append({'id':b['id'],'image_id':b['sop_instance_uid'],'category_id':l['disease_type_id'],'bbox':[b['x_min'],b['y_min'],w,h],'area':w*h,'iscrowd':0})
  return {'images':images,'annotations':anns,'categories':[{'id':d['id'],'name':d['disease_name']} for d in s['diseases']]}
 out=io.StringIO();writer=csv.writer(out);writer.writerow(['record_type','study_id','series_id','disease_type','target_key','lesion_instance_id','sop_instance_uid','x_min','y_min','x_max','y_max','attributes_json'])
 for a in s['assessments']:writer.writerow(['overall',a['study_id'],'',a['disease_type_id'],a['target_key'],'','','','','','',json.dumps(a.get('attributes_json',{}),ensure_ascii=False)])
 for b in s['boxes']:
  l=get('lesions',b['lesion_instance_id']);writer.writerow(['box',l['study_id'],l['series_id'],l['disease_type_id'],'',l['id'],b['sop_instance_uid'],*[b[k] for k in ['x_min','y_min','x_max','y_max']],json.dumps(l.get('attributes_json',{}),ensure_ascii=False)])
 return Response('\ufeff'+out.getvalue(),media_type='text/csv')
