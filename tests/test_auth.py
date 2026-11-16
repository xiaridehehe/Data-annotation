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

def register(c,name='tester'):
    return c.post('/api/auth/register',json=dict(username=name,password='StrongTest123',display_name='测试人员'))

BASE='/api/workspaces/00000000-0000-4000-8000-000000000001'

def test_register_login_cookie_logout_and_protection(clients):
    a,b,engine=clients
    assert a.get(BASE+'/state').status_code==401
    assert a.get('/api/auth/me').status_code==401
    response=register(a)
    assert response.status_code==200
    assert 'password_hash' not in response.text
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert a.get('/api/auth/me').json()['user']['username']=='tester'
    assert a.get(BASE+'/state').status_code==200
    assert b.get(BASE+'/state').status_code==401
    assert register(b,'TESTER').status_code==409
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
    assert register(a,'first').status_code==200
    assert register(b,'second').status_code==200
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
    assert a.post('/api/auth/register',json={'username':'abc','password':'invalid!','display_name':'a'}).status_code==422
    assert register(a).status_code==200
    assert b.post('/api/auth/login',headers={'Origin':'https://untrusted.example'},json={'username':'tester','password':'StrongTest123'}).status_code==403
    assert a.post(BASE+'/changes',headers={'Origin':'https://untrusted.example'},json={'operations':[]}).status_code==403
    with engine.begin() as c:
        c.execute(update(m.user_sessions).values(expires_at=datetime.now()-timedelta(days=8)))
    assert a.get(BASE+'/state').status_code==401


def test_simple_alphanumeric_account(clients):
    a,b,_=clients
    assert register(a,'1').status_code==200
    assert register(b,'aB123').status_code==200
    assert a.post('/api/auth/register',json={'username':'a_b','password':'StrongTest123','display_name':'name'}).status_code==422


def test_simple_alphanumeric_password(clients):
    a,b,_=clients
    assert a.post('/api/auth/register',json={'username':'simple','password':'1','display_name':'name'}).status_code==200
    assert b.post('/api/auth/login',json={'username':'simple','password':'1'}).status_code==200
    for password in ('','abc!','abc def'):
        assert b.post('/api/auth/register',json={'username':'other','password':password,'display_name':'name'}).status_code==422
