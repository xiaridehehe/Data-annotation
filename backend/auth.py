"""Password authentication with revocable, hashed, HttpOnly-cookie sessions."""
import hashlib
import hmac
import secrets
import re
import os
import time
from threading import Lock
from collections import OrderedDict, deque
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError
from backend import models as m

engine=None
router=APIRouter(prefix='/api/auth')
COOKIE='knee_session'
TTL=7*24*60*60
_attempts=OrderedDict()
_attempt_lock=Lock()

def limit_attempts(request,kind,limit):
    key=(request.client.host if request.client else 'unknown',kind)
    tick=time.monotonic()
    with _attempt_lock:
        bucket=_attempts.setdefault(key,deque())
        _attempts.move_to_end(key)
        while bucket and bucket[0]<=tick-60: bucket.popleft()
        if len(bucket)>=limit: raise HTTPException(429,'操作过于频繁，请稍后重试',headers={'Retry-After':'60'})
        bucket.append(tick)
        while len(_attempts)>2048: _attempts.popitem(last=False)


def now(): return datetime.now(timezone.utc).replace(tzinfo=None)

def password_hash(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'

def verify(password,encoded):
    try:
        algorithm,rounds,salt,digest=encoded.split('$')
        return algorithm=='pbkdf2_sha256' and hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(rounds)).hex(),digest)
    except (ValueError,TypeError): return False

DUMMY=password_hash('invalid-user-dummy-password')

def safe_origin(request):
    origin=request.headers.get('origin')
    allowed={str(request.base_url).rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173'}
    allowed.update(x.strip() for x in os.environ.get('ANNOTATION_ALLOWED_ORIGINS','').split(',') if x.strip())
    if origin and origin not in allowed: raise HTTPException(403,'请求来源不允许')

def public(user):
    return dict(id=user['id'],username=user['username'],display_name=user['display_name'])

def require_user(request:Request):
    if request.method not in ('GET','HEAD','OPTIONS'): safe_origin(request)
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>256: raise HTTPException(401,'请先登录')
    digest=hashlib.sha256(token.encode()).hexdigest()
    with engine.connect() as c:
        row=c.execute(select(m.users).join(m.user_sessions,m.users.c.id==m.user_sessions.c.user_id).where(
            m.user_sessions.c.token_hash==digest,m.user_sessions.c.expires_at>now(),m.users.c.active.is_(True))).mappings().first()
    if row is None: raise HTTPException(401,'登录已过期，请重新登录')
    return dict(row)

def current_actor(user=Depends(require_user)): return user['username']

def session(c,user,response):
    token=secrets.token_urlsafe(32)
    c.execute(delete(m.user_sessions).where(m.user_sessions.c.expires_at<=now()))
    c.execute(m.user_sessions.insert().values(user_id=user['id'],token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=now()+timedelta(seconds=TTL)))
    response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,samesite='strict',secure=os.environ.get('ANNOTATION_COOKIE_SECURE')=='1',path='/')
    response.headers['Cache-Control']='no-store'
    return {'user':public(user)}

def credentials(payload):
    username=payload.get('username','')
    password=payload.get('password','')
    if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9]{1,64}',username):
        raise HTTPException(422,'账号只允许字母和数字，最多 64 位')
    if not isinstance(password,str) or not re.fullmatch(r'[A-Za-z0-9]{1,128}',password):
        raise HTTPException(422,'密码只允许字母和数字，最多 128 位')
    return username.lower(),password

@router.post('/register')
def register(payload:dict,request:Request,response:Response):
    safe_origin(request);limit_attempts(request,'register',20);username,password=credentials(payload)
    display=payload.get('display_name',username)
    if not isinstance(display,str) or not display.strip() or len(display)>128: raise HTTPException(422,'请输入姓名或工号（最多128字）')
    encoded=password_hash(password)
    try:
        with engine.begin() as c:
            pk=c.execute(m.users.insert().values(username=username,display_name=display.strip(),password_hash=encoded,active=True)).inserted_primary_key[0]
            user=c.execute(select(m.users).where(m.users.c.id==pk)).mappings().one()
            return session(c,user,response)
    except IntegrityError: raise HTTPException(409,'该账号已注册')

@router.post('/login')
def login(payload:dict,request:Request,response:Response):
    safe_origin(request);limit_attempts(request,'login',30);username,password=credentials(payload)
    with engine.begin() as c:
        user=c.execute(select(m.users).where(m.users.c.username==username)).mappings().first()
        valid=verify(password,user['password_hash'] if user else DUMMY)
        if not valid or not user or not user['active']: raise HTTPException(401,'账号或密码错误')
        return session(c,user,response)

@router.get('/me')
def me(response:Response,user=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    return {'user':public(user)}

@router.post('/logout')
def logout(request:Request,response:Response):
    safe_origin(request)
    token=request.cookies.get(COOKIE,'')
    with engine.begin() as c:
        c.execute(delete(m.user_sessions).where(m.user_sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    response.delete_cookie(COOKIE,path='/');return {'ok':True}
