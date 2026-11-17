from datetime import date
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,update
from sqlalchemy.pool import StaticPool
from backend import models as m,auth,workflow,relational_api

@pytest.fixture(autouse=True)
def restore_router_engines():
    old_auth,old_workflow=auth.engine,workflow.engine
    yield
    auth.engine,workflow.engine=old_auth,old_workflow

def app_client():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    m.metadata.create_all(engine);auth.engine=engine;workflow.engine=engine
    app=FastAPI();app.include_router(auth.router);app.include_router(auth.admin_router);app.include_router(workflow.router)
    client=TestClient(app);client.app.state.test_engine=engine
    return client,engine

def register(client,name):
    with client.app.state.test_engine.begin() as db:
        db.execute(m.users.insert().values(username=name,display_name=name,
            password_hash=auth.password_hash('pass123'),role='ANNOTATOR',active=True))
    result=client.post('/api/auth/login',json={'username':name,'password':'pass123'})
    assert result.status_code==200

def seed_complete(engine,series_count=3):
    with engine.begin() as c:
        wid=c.execute(m.workspaces.insert().values(public_id='00000000-0000-4000-8000-000000000001',name='测试')).inserted_primary_key[0]
        pid=c.execute(m.patients.insert().values(workspace_id=wid,client_id='p1',patient_code='P1',version=1)).inserted_primary_key[0]
        stid=c.execute(m.studies.insert().values(workspace_id=wid,patient_id=pid,study_uid='1.2.3',description='检查',study_date=date.today(),version=1)).inserted_primary_key[0]
        did=c.execute(m.diseases.insert().values(workspace_id=wid,code='CUSTOM',name='测试标注',box_policy='NONE',overall_schema=[],lesion_schema=[],target_keys=['OVERALL'],active=True,version=1)).inserted_primary_key[0]
        for index in range(series_count):
            sid=c.execute(m.series.insert().values(study_id=stid,series_uid=f'1.2.3.{index+1}',series_number=index+1,description=f'序列{index+1}',modality='MR',plane='AXIAL',version=1)).inserted_primary_key[0]
            c.execute(m.assessments.insert().values(series_id=sid,disease_id=did,target_key='OVERALL',attributes={},status='COMPLETE',version=1))

def test_three_series_submit_reject_resubmit_and_approve():
    c,engine=app_client();register(c,'annotator');seed_complete(engine,2)
    with engine.begin() as db: db.execute(update(m.users).where(m.users.c.username=='annotator').values(role='ANNOTATOR'))
    base='/api/workspaces/00000000-0000-4000-8000-000000000001'
    failed=c.post(base+'/studies/1.2.3/submit')
    assert failed.status_code==422 and '至少需要完成 3 个序列' in str(failed.json())
    with engine.begin() as db:
        stid=db.execute(select(m.studies.c.id)).scalar()
        sid=db.execute(m.series.insert().values(study_id=stid,series_uid='1.2.3.3',series_number=3,description='序列3',modality='MR',plane='AXIAL',version=1)).inserted_primary_key[0]
        did=db.execute(select(m.diseases.c.id)).scalar()
        db.execute(m.assessments.insert().values(series_id=sid,disease_id=did,target_key='OVERALL',attributes={},status='COMPLETE',version=1))
    submitted=c.post(base+'/studies/1.2.3/submit');assert submitted.status_code==200
    submission_id=submitted.json()['submission']['id']
    with engine.begin() as db:
        assessment=db.execute(select(m.assessments)).mappings().first()
        relational_api.ensure_editable(db,'assessments',assessment,{'role':'REVIEWER'})
        relational_api.ensure_editable(db,'assessments',assessment,{'role':'ANNOTATOR'})
    c.post('/api/auth/logout');register(c,'reviewer')
    with engine.begin() as db: db.execute(update(m.users).where(m.users.c.username=='reviewer').values(role='REVIEWER'))
    assert c.post(base+f'/submissions/{submission_id}/review',json={'action':'reject','reason':''}).status_code==422
    rejected=c.post(base+f'/submissions/{submission_id}/review',json={'action':'reject','reason':'属性需要复核'})
    assert rejected.status_code==200 and rejected.json()['submission']['status']=='REJECTED'
    c.post('/api/auth/logout');login=c.post('/api/auth/login',json={'username':'annotator','password':'pass123'});assert login.status_code==200
    resubmitted=c.post(base+'/studies/1.2.3/submit');assert resubmitted.json()['submission']['revision']==2
    c.post('/api/auth/logout');c.post('/api/auth/login',json={'username':'reviewer','password':'pass123'})
    approved=c.post(base+f'/submissions/{submission_id}/review',json={'action':'approve'})
    assert approved.status_code==200 and approved.json()['submission']['status']=='APPROVED'
    with engine.begin() as db:
        study_id=db.execute(select(m.studies.c.id)).scalar()
        relational_api.mark_submission_changed(db,{study_id},{'role':'ANNOTATOR'})
        changed=db.execute(select(m.submissions)).mappings().one()
        assert changed['status']=='SUBMITTED' and changed['revision']==2 and changed['reviewer_user_id'] is None
        history=db.execute(select(m.submission_review_history).order_by(m.submission_review_history.c.id)).mappings().all()
        assert [item['action'] for item in history]==['SUBMIT','REJECT','RESUBMIT','APPROVE']
        assert [item['revision'] for item in history]==[1,1,2,2]

def test_admin_user_management_and_last_admin_guard():
    c,engine=app_client();register(c,'rootadmin')
    with engine.begin() as db: db.execute(update(m.users).where(m.users.c.username=='rootadmin').values(role='ADMIN'))
    created=c.post('/api/admin/users',json={'username':'review1','password':'pass123','display_name':'审核员','role':'REVIEWER'})
    assert created.status_code==200 and created.json()['user']['role']=='REVIEWER'
    user_id=created.json()['user']['id']
    assert len(c.get('/api/admin/users').json()['users'])==2
    assert c.put(f'/api/admin/users/{user_id}',json={'display_name':'审核员甲','active':True}).status_code==200
    assert c.delete(f'/api/admin/users/{user_id}').status_code==200
    me=c.get('/api/auth/me').json()['user']
    assert c.put(f"/api/admin/users/{me['id']}",json={'role':'ANNOTATOR'}).status_code==409

def test_extra_unannotated_series_do_not_block_submission():
    c,engine=app_client();register(c,'annotator2')
    with engine.begin() as db: db.execute(update(m.users).where(m.users.c.username=='annotator2').values(role='ANNOTATOR'))
    seed_complete(engine,3)
    with engine.begin() as db:
        stid=db.execute(select(m.studies.c.id)).scalar()
        for index in (4,5):
            db.execute(m.series.insert().values(study_id=stid,series_uid=f'1.2.3.{index}',series_number=index,description=f'额外序列{index}',modality='MR',plane='UNKNOWN',version=1))
    base='/api/workspaces/00000000-0000-4000-8000-000000000001'
    assert c.post(base+'/studies/1.2.3/submit').status_code==200
