import json,csv,io
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
import backend.main as m

def test_series_export_complete_and_incomplete(tmp_path,monkeypatch):
 engine=create_engine('sqlite:///'+str(tmp_path/'export.db'))
 monkeypatch.setattr(m,'engine',engine)
 with engine.begin() as db:db.execute(text('CREATE TABLE records (kind TEXT,id TEXT PRIMARY KEY,data TEXT NOT NULL)'))
 m.put('patients',{'id':'patient'})
 m.put('studies',{'id':'study','patient_id':'patient'})
 for sid in ['selected','other']:
  m.put('series',{'id':sid,'study_id':'study','description':sid})
  m.put('instances',{'id':'image-'+sid,'series_id':sid,'width':100,'height':100,'order':0,'path':'private'})
 m.put('diseases',{'id':'custom','disease_name':'custom','overall_fields':[],'lesion_fields':[{'field_code':'location','field_name':'location','required':True}],'box_policy':'REQUIRED'})
 m.put('lesions',{'id':'lesion','study_id':'study','series_id':'selected','disease_type_id':'custom','attributes_json':{}})
 m.put('boxes',{'id':'box','lesion_instance_id':'lesion','sop_instance_uid':'image-selected','slice_index':0,'x_min':10,'y_min':20,'x_max':40,'y_max':60,'image_width':100,'image_height':100})
 c=TestClient(m.app)
 for fmt in ['json','csv','coco']:assert c.get('/api/export/'+fmt,params={'series_id':'selected'}).status_code==422
 lesion=m.get('lesions','lesion');lesion['attributes_json']={'location':'femur'};m.put('lesions',lesion)
 data=c.get('/api/export/json?series_id=selected').json()
 assert len(data['series'])==len(data['instances'])==len(data['boxes'])==1
 assert data['patients'][0]['id']=='patient' and data['studies'][0]['id']=='study'
 assert 'path' not in data['instances'][0]
 assert data['lesions'][0]['attributes_json']['location']=='femur'
 coco=c.get('/api/export/coco?series_id=selected').json()
 assert coco['annotations'][0]['bbox']==[10,20,30,40]
 assert isinstance(coco['annotations'][0]['category_id'],int)
 assert coco['images'][0]['patient_id']=='patient'
 records=list(csv.DictReader(io.StringIO(c.get('/api/export/csv?series_id=selected').text.lstrip('\ufeff'))))
 assert records[0]['patient_id']=='patient' and records[0]['sop_instance_uid']=='image-selected'
 assert json.loads(records[0]['attributes_json'])=={'location':'femur'}
