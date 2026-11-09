from fastapi.testclient import TestClient
from backend.main import app
c=TestClient(app)
def test_assessment_unique():
 d=dict(study_id='test',disease_type_id='ACL_INJURY',target_key='ACL',attributes_json={'损伤程度':'部分撕裂'})
 a=c.put('/api/assessments',json=d).json();d['attributes_json']={'损伤程度':'完全断裂'}
 b=c.put('/api/assessments',json=d).json()
 assert a['id']==b['id']
 assert len([x for x in c.get('/api/state').json()['assessments'] if x['study_id']=='test'])==1
 c.delete('/api/assessments/'+a['id'])
def test_no_box_diseases():
 for code in ['JOINT_EFFUSION','SYNOVIAL_ABNORMALITY']:
  assert c.put('/api/lesions',json=dict(disease_type_id=code)).status_code==422
def test_exports():
 for fmt in ['json','csv','coco']:assert c.get('/api/export/'+fmt).status_code==200
