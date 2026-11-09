import uuid
from fastapi.testclient import TestClient
from backend.main import app,put,get
c=TestClient(app)
def test_save_and_remove_restore():
 u='test-'+str(uuid.uuid4());put('patients',{'id':u});put('studies',{'id':u+'study','patient_id':u});put('series',{'id':u+'series','study_id':u+'study'});put('assessments',{'id':u+'assessment','study_id':u+'study','disease_type_id':'ACL_INJURY','target_key':'ACL','attributes_json':{'severity':'partial'}})
 saved=c.post('/api/project/save');assert saved.status_code==200;assert get('snapshots',saved.json()['id'])
 r=c.delete('/api/imported/series/'+u+'series');assert r.status_code==200;assert get('series',u+'series') is None;assert get('assessments',u+'assessment')
 assert c.post('/api/imported/restore/'+r.json()['archive_id']).status_code==200;assert get('series',u+'series')
 r=c.delete('/api/imported/patients/'+u);assert r.status_code==200;assert not get('assessments',u+'assessment');assert not get('studies',u+'study')
 # Remove only the synthetic fixture archive and snapshot created by this test.
 from backend.main import engine,text
 with engine.begin() as db:
  for id in [r.json()['archive_id'],saved.json()['id']]:db.execute(text('DELETE FROM records WHERE id=:i'),{'i':id})
