import uuid
from fastapi.testclient import TestClient
from backend.main import app, get
c=TestClient(app)
def test_browser_project_persistence_and_isolation():
 a,b=str(uuid.uuid4()),str(uuid.uuid4())
 state={k:[] for k in ['patients','studies','series','instances','diseases','assessments','lesions','boxes','groups','segmentations']}
 state['boxes']=[{'id':'box','x_min':1}]
 assert c.put('/api/browser-project/'+a,json=state).status_code==200
 assert get('browser_projects',a)['state']['boxes']==state['boxes']
 assert c.get('/api/browser-project/'+a).json()['state']==state
 assert c.get('/api/browser-project/'+b).json()['state'] is None
 state['instances']=[{'PixelData':'forbidden'}]
 assert c.put('/api/browser-project/'+a,json=state).status_code==422
 assert c.get('/api/browser-project/'+a).json()['state']['instances']==[]
