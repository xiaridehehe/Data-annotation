"""Authentication integration tests using real password checks and cookie sessions."""
import pytest
from datetime import datetime,timedelta
from sqlalchemy import create_engine,select,update
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import models as m,auth,relational_api as api

@pytest.fixture
def clients(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'accounts.db'))
    m.metadata.create_all(engine)
    monkeypatch.setattr(auth,'engine',engine);monkeypatch.setattr(api,'engine',engine)
    app=FastAPI();app.include_router(auth.router);app.include_router(api.router)
    with TestClient(app) as a,TestClient(app) as b:
        yield a,b,engine
    engine.dispose()

def seed_user(engine,name='tester',password='StrongTest123'):
    with engine.begin() as c:
        c.execute(m.users.insert().values(username=name.lower(),display_name='测试人员',
            password_hash=auth.password_hash(password),role='ANNOTATOR',active=True))

BASE='/api/workspaces/00000000-0000-4000-8000-000000000001'

def test_login_cookie_logout_and_protection(clients):
    a,b,engine=clients
    assert a.get(BASE+'/state').status_code==401
    assert a.get('/api/auth/me').status_code==401
    assert a.post('/api/auth/register').status_code==403
    seed_user(engine)
    response=a.post('/api/auth/login',json={'username':'tester','password':'StrongTest123'})
    assert response.status_code==200
    assert 'password_hash' not in response.text
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert a.get('/api/auth/me').json()['user']['username']=='tester'
    assert a.get(BASE+'/state').status_code==200
    assert b.get(BASE+'/state').status_code==401
    assert b.post('/api/auth/login',json={'username':'tester','password':'WrongPassword123'}).status_code==401
    assert b.post('/api/auth/login',json={'username':'TESTER','password':'StrongTest123'}).status_code==200
    assert b.get(BASE+'/state').status_code==200
    with engine.connect() as c:
        row=c.execute(select(m.users)).mappings().one()
        assert row['password_hash']!='StrongTest123'
        assert auth.verify('StrongTest123',row['password_hash'])
        session=c.execute(select(m.user_sessions)).mappings().first()
        assert session['token_hash']!=a.cookies.get(auth.COOKIE)
    cookie=a.cookies.get(auth.COOKIE)
    assert a.post('/api/auth/logout').status_code==200
    a.cookies.set(auth.COOKIE,cookie)
    assert a.get(BASE+'/state').status_code==401
    assert b.get(BASE+'/state').status_code==200


def test_actor_cannot_be_spoofed_and_shared_latest(clients):
    a,b,engine=clients
    seed_user(engine,'first');seed_user(engine,'second')
    assert a.post('/api/auth/login',json={'username':'first','password':'StrongTest123'}).status_code==200
    assert b.post('/api/auth/login',json={'username':'second','password':'StrongTest123'}).status_code==200
    assert a.get(BASE+'/state').status_code==200
    record=dict(id='patient-key',patient_code='P1',issuer='hospital')
    def save(c,version,code):
        return c.post(BASE+'/changes',headers={'X-Operator':'someone-else'},json={'operations':[dict(kind='patients',record={**record,'patient_code':code},expected_version=version)]})
    assert save(a,0,'P1').status_code==200
    assert b.get(BASE+'/state').json()['state']['patients'][0]['patient_code']=='P1'
    assert save(b,1,'P2').status_code==200
    assert save(a,1,'P3').status_code==409
    assert a.get(BASE+'/state').json()['state']['patients'][0]['patient_code']=='P2'
    with engine.connect() as c:
        logs=c.execute(select(m.change_logs).order_by(m.change_logs.c.id)).mappings().all()
        assert [x['actor'] for x in logs]==['first','second']
        assert all(x['actor_user_id'] for x in logs)
        ids=c.execute(select(m.users.c.id,m.users.c.username)).all()
        assert dict(ids)[logs[0]['actor_user_id']]=='first'


def test_expiry_validation_and_cross_origin(clients):
    a,b,engine=clients
    assert a.post('/api/auth/register',json={'username':'abc','password':'invalid!','display_name':'a'}).status_code==403
    seed_user(engine)
    assert a.post('/api/auth/login',json={'username':'tester','password':'StrongTest123'}).status_code==200
    assert b.post('/api/auth/login',headers={'Origin':'https://untrusted.example'},json={'username':'tester','password':'StrongTest123'}).status_code==403
    assert a.post(BASE+'/changes',headers={'Origin':'https://untrusted.example'},json={'operations':[]}).status_code==403
    with engine.begin() as c:
        c.execute(update(m.user_sessions).values(expires_at=datetime.now()-timedelta(days=8)))
    assert a.get(BASE+'/state').status_code==401


def test_simple_alphanumeric_account(clients):
    a,b,engine=clients
    seed_user(engine,'1');seed_user(engine,'aB123')
    assert a.post('/api/auth/login',json={'username':'1','password':'StrongTest123'}).status_code==200
    assert b.post('/api/auth/login',json={'username':'aB123','password':'StrongTest123'}).status_code==200


def test_simple_alphanumeric_password(clients):
    a,b,engine=clients
    seed_user(engine,'simple','1')
    assert b.post('/api/auth/login',json={'username':'simple','password':'1'}).status_code==200
    for password in ('','abc!','abc def'):
        assert b.post('/api/auth/login',json={'username':'simple','password':password}).status_code in (401,422)
