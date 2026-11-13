"""Integration tests for the current relational browser API."""
import uuid
import pytest
from sqlalchemy import create_engine, select, event
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import models as m, relational_api as api

@pytest.fixture
def client(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'relational.db'))
    @event.listens_for(engine,'connect')
    def foreign_keys(dbapi, record): dbapi.execute('PRAGMA foreign_keys=ON')
    m.metadata.create_all(engine)
    monkeypatch.setattr(api,'engine',engine)
    app=FastAPI();app.include_router(api.router)
    with TestClient(app,headers={'X-Operator':'tester'}) as c: yield c,engine
    engine.dispose()

def operation(kind, record, version=0, action='upsert'):
    return dict(kind=kind,record=record,expected_version=version,action=action)

def setup(c):
    base='/api/workspaces/'+str(uuid.uuid4())
    assert c.get(base+'/state').status_code==200
    ops=[operation('patients',dict(id='patient-key',patient_code='P001',issuer='hospital'))]
    for n in (1,2):
        ops.extend([operation('studies',dict(id=f'1.2.{n}',patient_id='patient-key',date='20260101',description=f'check{n}')),
            operation('series',dict(id=f'1.2.{n}.1',study_id=f'1.2.{n}',description='series',orientation='SAG')),
            operation('instances',dict(id=f'1.2.{n}.1.1',series_id=f'1.2.{n}.1',width=100,height=100,order=0))])
    r=c.post(base+'/changes',json={'operations':ops});assert r.status_code==200,r.text
    return base

def test_same_patient_multiple_studies_and_scoped_ids(client):
    c,engine=client;a=setup(c);b=setup(c)
    data=c.get(a+'/state').json()['state']
    assert len(data['patients'])==1 and len(data['studies'])==2
    assert len({s['study_id'] for s in data['series']})==2
    with engine.connect() as db:
        assert len(db.execute(select(m.studies)).all())==4
        assert set(m.metadata.tables)=={'workspaces','patients','studies','series','images','diseases','assessments','lesions','boxes','change_logs'}
        assert all('data' not in t.c for t in m.metadata.tables.values())

def assessment(side, value, series='1.2.1.1'):
    return dict(id=series+'|MENISCUS_INJURY|'+side,series_id=series,disease_type_id='MENISCUS_INJURY',target_key=side,attributes_json={'损伤程度':value})

def test_meniscus_targets_and_row_conflicts(client):
    c,_=client;base=setup(c)
    prepare_assessment_boxes(c,base)
    inner=assessment('MEDIAL_MENISCUS','部分撕裂');outer=assessment('LATERAL_MENISCUS','正常')
    for record in (inner,outer):
        assert c.post(base+'/changes',json={'operations':[operation('assessments',record)]}).status_code==200
    inner['attributes_json']={'损伤程度':'完全断裂'}
    assert c.post(base+'/changes',json={'operations':[operation('assessments',inner,1)]}).status_code==200
    # Updating the other side still succeeds using its own unchanged version.
    assert c.post(base+'/changes',json={'operations':[operation('assessments',outer,1)]}).status_code==200
    assert c.post(base+'/changes',json={'operations':[operation('assessments',inner,1)]}).status_code==409
    bad=assessment('OVERALL','正常')
    assert c.post(base+'/changes',json={'operations':[operation('assessments',bad)]}).status_code==422
    rows=c.get(base+'/state').json()['state']['assessments']
    assert len(rows)==2 and {x['target_key'] for x in rows}=={'MEDIAL_MENISCUS','LATERAL_MENISCUS'}
    assert next(x for x in rows if x['target_key']=='MEDIAL_MENISCUS')['attributes_json']['损伤程度']=='完全断裂'

def lesion_record():
    return dict(id=str(uuid.uuid4()),series_id='1.2.1.1',disease_type_id='MENISCUS_INJURY',target_key='MEDIAL_MENISCUS',attributes_json={'半月板类型':'内侧半月板'},color='#FF8800')

def test_boxes_constraints_rollback_and_restore(client):
    c,engine=client;base=setup(c);lesion=lesion_record()
    box=dict(id=str(uuid.uuid4()),lesion_instance_id=lesion['id'],sop_instance_uid='1.2.1.1.1',x_min=1,y_min=2,x_max=30,y_max=40)
    assert c.post(base+'/changes',json={'operations':[operation('lesions',lesion),operation('boxes',box)]}).status_code==200
    # Cross-series association and invalid bounds are rejected by the server.
    assert c.post(base+'/changes',json={'operations':[operation('boxes',{**box,'sop_instance_uid':'1.2.2.1.1'},1)]}).status_code==422
    assert c.post(base+'/changes',json={'operations':[operation('boxes',{**box,'x_max':101},1)]}).status_code==422
    # A later failure rolls back the preceding valid update in the same transaction.
    assert c.post(base+'/changes',json={'operations':[operation('lesions',{**lesion,'color':'#000000'},1),operation('boxes',{**box,'x_max':101},1)]}).status_code==422
    assert c.get(base+'/state').json()['state']['lesions'][0]['color']=='#FF8800'
    assert c.post(base+'/changes',json={'operations':[operation('boxes',box,1,'delete')]}).status_code==200
    state=c.get(base+'/state').json()['state'];assert not state['boxes'] and state['_deleted']['boxes'][0]['version']==2
    assert c.post(base+'/changes',json={'operations':[operation('boxes',box,2)]}).status_code==200
    assert c.get(base+'/state').json()['state']['boxes'][0]['version']==3
    # Removing one study hides only its descendants, then restore reveals the same rows.
    result=c.post(base+'/visibility',json=dict(kind='studies',id='1.2.1',expected_version=1))
    assert result.status_code==200
    state=c.get(base+'/state').json()['state'];assert len(state['studies'])==1 and not state['boxes']
    assert c.post(base+'/visibility',json=dict(kind='studies',id='1.2.1',expected_version=2,restore=True)).status_code==200
    assert len(c.get(base+'/state').json()['state']['boxes'])==1
    with engine.connect() as db:
        row=db.execute(select(m.boxes)).mappings().one()
        assert row['x_max']==30 and row['lesion_id'] and row['image_id']

def test_scope_and_missing_version(client):
    c,_=client;a=setup(c);b=setup(c)
    lesion=lesion_record()
    assert c.post(a+'/changes',json={'operations':[operation('lesions',lesion)]}).status_code==200
    box=dict(id=str(uuid.uuid4()),lesion_instance_id=lesion['id'],sop_instance_uid='1.2.1.1.1',x_min=1,y_min=1,x_max=5,y_max=5)
    assert c.post(b+'/changes',json={'operations':[operation('boxes',box)]}).status_code==404
    assert c.post(a+'/changes',json={'operations':[dict(kind='boxes',record=box)]}).status_code==422


def test_existing_assessments_gets_missing_soft_delete_column(tmp_path,monkeypatch):
    from sqlalchemy import text, inspect
    from backend.database import create_database_engine
    url='sqlite:///'+str(tmp_path/'existing.db')
    db=create_engine(url)
    with db.begin() as c:
        c.execute(text('CREATE TABLE assessments (id INTEGER PRIMARY KEY)'))
    db.dispose()
    monkeypatch.setenv('ANNOTATION_DATABASE_URL',url)
    db=create_database_engine()
    assert 'deleted_at' in {c['name'] for c in inspect(db).get_columns('assessments')}
    db.dispose()
    db=create_database_engine()  # repeated startup is harmless
    db.dispose()


def test_reimport_restores_deleted_hierarchy_and_annotations(client):
    c,_=client;base=setup(c);lesion=lesion_record()
    box=dict(id=str(uuid.uuid4()),lesion_instance_id=lesion['id'],sop_instance_uid='1.2.1.1.1',x_min=1,y_min=2,x_max=20,y_max=30)
    assert c.post(base+'/changes',json={'operations':[operation('lesions',lesion),operation('boxes',box)]}).status_code==200
    for kind,key in [('series','1.2.1.1'),('studies','1.2.1')]:
        current=c.get(base+'/state').json()['state']
        row=next(x for x in current[kind] if x['id']==key)
        assert c.post(base+'/visibility',json=dict(kind=kind,id=key,expected_version=row['version'])).status_code==200
        assert not c.get(base+'/state').json()['state']['boxes']
        r=c.post(base+'/reimport',json={'series_uids':['1.2.1.1']})
        assert r.status_code==200,r.text
        state=r.json()['state'];assert len(state['studies'])==2
        assert state['boxes'][0]['id']==box['id']
        assert state['lesions'][0]['version']==1
        image=next(x for x in state['instances'] if x['id']=='1.2.1.1.1')
        assert c.post(base+'/changes',json={'operations':[operation('instances',image,image['version'])]}).status_code==200
    assert c.post(base+'/reimport',json={'series_uids':['1.2.1.1']}).json()['state']['boxes'][0]['version']==1


def test_actor_audit_and_latest_result(client):
    from urllib.parse import quote
    c,engine=client;base=setup(c)
    prepare_assessment_boxes(c,base)
    value=assessment('MEDIAL_MENISCUS','部分撕裂')
    assert c.post(base+'/changes',headers={'X-Operator':quote('张医生')},json={'operations':[operation('assessments',value)]}).status_code==200
    value['attributes_json']={'损伤程度':'完全断裂'}
    assert c.post(base+'/changes',headers={'X-Operator':'doctor-B'},json={'operations':[operation('assessments',value,1)]}).status_code==200
    assert c.post(base+'/changes',headers={'X-Operator':'doctor-C'},json={'operations':[operation('assessments',value,1)]}).status_code==409
    assert c.post(base+'/changes',headers={'X-Operator':''},json={'operations':[]}).status_code==422
    with engine.connect() as db:
        logs=db.execute(select(m.change_logs).where(m.change_logs.c.entity_type=='assessments').order_by(m.change_logs.c.id)).mappings().all()
        assert [r['actor'] for r in logs]==['张医生','doctor-B']
        assert logs[0]['before_value'] is None
        assert logs[1]['before_value']['attributes']['损伤程度']=='部分撕裂'
        assert logs[1]['after_value']['attributes']['损伤程度']=='完全断裂'
    assert c.get(base+'/state').json()['state']['assessments'][0]['attributes_json']['损伤程度']=='完全断裂'


def prepare_assessment_boxes(c,base):
    for side in ('MEDIAL_MENISCUS','LATERAL_MENISCUS'):
        l={**lesion_record(),'target_key':side}
        b=dict(id=str(uuid.uuid4()),lesion_instance_id=l['id'],sop_instance_uid='1.2.1.1.1',x_min=1,y_min=1,x_max=10,y_max=10)
        assert c.post(base+'/changes',json={'operations':[operation('lesions',l),operation('boxes',b)]}).status_code==200


def test_assessment_requires_box_for_same_target(client):
    c,_=client;base=setup(c)
    value=assessment('MEDIAL_MENISCUS','部分撕裂')
    assert c.post(base+'/changes',json={'operations':[operation('assessments',value)]}).status_code==422
    l=lesion_record()
    assert c.post(base+'/changes',json={'operations':[operation('lesions',l)]}).status_code==200
    assert c.post(base+'/changes',json={'operations':[operation('assessments',value)]}).status_code==422
    b=dict(id=str(uuid.uuid4()),lesion_instance_id=l['id'],sop_instance_uid='1.2.1.1.1',x_min=1,y_min=1,x_max=10,y_max=10)
    assert c.post(base+'/changes',json={'operations':[operation('boxes',b)]}).status_code==200
    assert c.post(base+'/changes',json={'operations':[operation('assessments',value)]}).status_code==200
    assert c.post(base+'/changes',json={'operations':[operation('assessments',assessment('LATERAL_MENISCUS','正常'))]}).status_code==422
    direct=dict(id='1.2.1.1|JOINT_EFFUSION|OVERALL',series_id='1.2.1.1',disease_type_id='JOINT_EFFUSION',target_key='OVERALL',attributes_json={'积液程度':'无积液'})
    assert c.post(base+'/changes',json={'operations':[operation('assessments',direct)]}).status_code==200
