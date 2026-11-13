"""Relational API adapter. Public DICOM/client IDs stay stable in the viewer."""
import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from backend import models as m

router = APIRouter(prefix='/api/workspaces')
engine = None
KINDS = tuple(m.TABLES)

def fail(message, code=422):
    raise HTTPException(code, message)

def stamp():
    return datetime.now(__import__('datetime').timezone.utc).replace(tzinfo=None)

def uuid_key(value):
    try: return str(uuid.UUID(str(value)))
    except (ValueError, TypeError): fail('无效的 UUID')

def workspace(c, public_id):
    public_id = uuid_key(public_id)
    row = c.execute(select(m.workspaces).where(m.workspaces.c.public_id == public_id)).mappings().first()
    if row is None:
        pk = c.execute(m.workspaces.insert().values(public_id=public_id, name='标注空间')).inserted_primary_key[0]
        configs = json.loads((Path(__file__).parents[1]/'frontend/diseases.json').read_text(encoding='utf-8'))
        for d in configs:
            c.execute(m.diseases.insert().values(workspace_id=pk, code=d['id'], name=d['disease_name'],
                box_policy=d['box_policy'], overall_schema=d['overall_fields'], lesion_schema=d['lesion_fields'],
                target_keys=['MEDIAL_MENISCUS','LATERAL_MENISCUS'] if d['id']=='MENISCUS_INJURY' else ['OVERALL'], active=True))
        row = c.execute(select(m.workspaces).where(m.workspaces.c.id==pk)).mappings().one()
    return row

def scoped(kind, wid):
    t=m.TABLES[kind]
    if kind in ('patients','studies','diseases'):
        return select(t).where(t.c.workspace_id==wid)
    if kind=='series':
        return select(t).join(m.studies, t.c.study_id==m.studies.c.id).where(m.studies.c.workspace_id==wid)
    return select(t).join(m.series,t.c.series_id==m.series.c.id).join(m.studies,m.series.c.study_id==m.studies.c.id).where(m.studies.c.workspace_id==wid)

def by_id(c, kind, wid, internal):
    return c.execute(scoped(kind,wid).where(m.TABLES[kind].c.id==internal)).mappings().first()

def lookup(c, kind, wid, key, required=True, lock=False):
    t=m.TABLES[kind]
    columns={'patients':'client_id','studies':'study_uid','series':'series_uid','instances':'sop_instance_uid',
             'diseases':'code','lesions':'public_id','boxes':'public_id'}
    if kind=='assessments':
        # Assessments are addressed by their natural key in the API adapter.
        parts=key.split('|')
        if len(parts)!=3: fail('无效的评估标识')
        se=lookup(c,'series',wid,parts[0]); disease=lookup(c,'diseases',wid,parts[1])
        stmt=scoped(kind,wid).where(t.c.series_id==se['id'],t.c.disease_id==disease['id'],t.c.target_key==parts[2])
    else:
        stmt=scoped(kind,wid).where(t.c[columns[kind]]==key)
    if lock: stmt=stmt.with_for_update()
    rows=c.execute(stmt).mappings().all()
    if len(rows)>1: fail('标识对应多个记录，影像层级存在冲突',409)
    if not rows:
        if required: fail('关联记录不存在：'+kind,404)
        return None
    return rows[0]

def active_series(c, wid, key):
    se=lookup(c,'series',wid,key,lock=True)
    st=by_id(c,'studies',wid,se['study_id'])
    if se['deleted_at'] or st['deleted_at']: fail('检查或序列已移除',409)
    return se

def limited(value, maximum, label, empty=False):
    if not isinstance(value,str) or len(value)>maximum or (not empty and not value): fail('无效的'+label)
    return value

def uid(value):
    value=limited(value,64,'DICOM UID')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+',value): fail('无效的 DICOM UID')
    return value

def attrs(value):
    if not isinstance(value,dict): fail('属性必须为对象')
    check_payload(value)
    return value

def check_payload(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.lower() in {'pixeldata','pixel_data','path','imageid','file','blob'}: fail('禁止上传影像文件或像素')
            check_payload(v)
    elif isinstance(value,list):
        for v in value: check_payload(v)

def target(d, disease):
    value=d.get('target_key','OVERALL')
    if disease['code']=='MENISCUS_INJURY' and value=='OVERALL':
        value={'内侧半月板':'MEDIAL_MENISCUS','外侧半月板':'LATERAL_MENISCUS'}.get(d.get('attributes_json',{}).get('半月板类型'), value)
    if value not in disease['target_keys']: fail('病种不允许此评估目标或尚未选择半月板侧别')
    return value

def values(c, kind, wid, d):
    key=limited(d.get('id'),512,'记录 ID')
    if kind=='patients':
        return dict(workspace_id=wid,client_id=limited(key,128,'患者内部标识'),
                    patient_code=limited(d['patient_code'],128,'患者编号') if d.get('patient_code') else None,issuer=limited(d['issuer'],128,'编号来源') if d.get('issuer') else None)
    if kind=='studies':
        patient=lookup(c,'patients',wid,d.get('patient_id'))
        date=d.get('date') or None
        try: date=datetime.strptime(date.replace('-',''),'%Y%m%d').date() if date else None
        except (ValueError,AttributeError): fail('检查日期格式错误')
        tm=d.get('study_time') or None
        try:
            if tm:
                parts=tm.split('.')
                tm=parts[0].ljust(6,'0')+('.'+parts[1] if len(parts)==2 else '')
                tm=datetime.strptime(tm,'%H%M%S.%f' if '.' in tm else '%H%M%S').time()
            else: tm=None
        except (ValueError,TypeError): fail('检查时间格式错误')
        return dict(workspace_id=wid,patient_id=patient['id'],study_uid=uid(key),study_date=date,study_time=tm,
                    accession_number=limited(d.get('accession_number','') or '',128,'申请号',True),description=limited(d.get('description',''),512,'检查描述',True))
    if kind=='series':
        st=lookup(c,'studies',wid,d.get('study_id'),lock=True)
        if st['deleted_at']: fail('检查已移除',409)
        try: number=int(d['number']) if d.get('number') not in ('',None) else None
        except (ValueError,TypeError): fail('序列编号必须是整数')
        plane=d.get('orientation','UNKNOWN')
        if plane not in ('SAG','COR','AX','OBLIQUE','UNKNOWN','未知'): fail('无效的影像方向')
        return dict(study_id=st['id'],series_uid=uid(key),series_number=number,
            description=limited(d.get('description',''),512,'序列描述',True),modality=limited(d.get('modality','MR'),16,'影像类型'),plane='UNKNOWN' if plane=='未知' else plane)
    if kind=='instances':
        se=active_series(c,wid,d.get('series_id'))
        for field in ('width','height'):
            if not isinstance(d.get(field),int) or isinstance(d[field],bool) or d[field]<=0: fail('影像尺寸必须为正整数')
        result=dict(series_id=se['id'],sop_instance_uid=uid(key),width=d['width'],height=d['height'],sort_order=d.get('order',0),instance_number=d.get('instance_number'))
        for name,columns in [('position',('position_x','position_y','position_z')),('orientation',('row_cosine_x','row_cosine_y','row_cosine_z','column_cosine_x','column_cosine_y','column_cosine_z')),('pixel_spacing',('pixel_spacing_row','pixel_spacing_column'))]:
            v=d.get(name,[])
            if v and (not isinstance(v,list) or len(v)!=len(columns)): fail('影像空间信息长度错误')
            result.update({column:(v[n] if v else None) for n,column in enumerate(columns)})
        for name,v in result.items():
            if name not in ('sop_instance_uid',) and v is not None and (not isinstance(v,(float,int)) or not math.isfinite(v)): fail('影像数值无效')
        return result
    if kind=='diseases':
        code=limited(key,64,'病种编码')
        if not re.fullmatch('[A-Za-z0-9_]+',code): fail('病种编码仅允许字母、数字、下划线')
        policy=d.get('box_policy','OPTIONAL')
        if policy not in ('NONE','OPTIONAL','REQUIRED'): fail('无效的画框规则')
        for field in ('overall_fields','lesion_fields'):
            if not isinstance(d.get(field),list): fail('表单配置必须为数组')
        return dict(workspace_id=wid,code=code,name=limited(d.get('disease_name'),128,'病种名称'),box_policy=policy,
            overall_schema=d['overall_fields'],lesion_schema=d['lesion_fields'],
            target_keys=['MEDIAL_MENISCUS','LATERAL_MENISCUS'] if code=='MENISCUS_INJURY' else ['OVERALL'],active=bool(d.get('active',True)))
    if kind in ('assessments','lesions'):
        se=active_series(c,wid,d.get('series_id')); disease=lookup(c,'diseases',wid,d.get('disease_type_id'),lock=True)
        if not disease['active']: fail('病种已停用')
        value=target(d,disease)
        if kind=='assessments' and disease['box_policy']!='NONE':
            exists=c.execute(select(m.boxes.c.id).join(m.lesions,m.boxes.c.lesion_id==m.lesions.c.id).where(
                m.lesions.c.series_id==se['id'],m.lesions.c.disease_id==disease['id'],
                m.lesions.c.target_key==value,m.lesions.c.deleted_at.is_(None),m.boxes.c.deleted_at.is_(None)).limit(1)).first()
            if not exists: fail('请先为当前病害及侧别绘制病灶框，再填写整体评估')
        result=dict(series_id=se['id'],disease_id=disease['id'],target_key=value,attributes=attrs(d.get('attributes_json',{})))
        if kind=='lesions':
            if disease['box_policy']=='NONE': fail('该病种不允许局部框标注')
            color=d.get('color','#FF8800')
            if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color): fail('颜色格式无效')
            result.update(public_id=uuid_key(key),color=color)
        else:
            status=d.get('status','DRAFT')
            if status not in ('DRAFT','COMPLETE'): fail('无效的评估状态')
            result['status']=status
            expected='|'.join([d['series_id'],d['disease_type_id'],value])
            if key!=expected: fail('整体评估 ID 与序列、病种、侧别不一致')
        return result
    if kind=='boxes':
        lesion=lookup(c,'lesions',wid,d.get('lesion_instance_id'),lock=True)
        if lesion['deleted_at']: fail('病灶已删除',409)
        se=by_id(c,'series',wid,lesion['series_id']);active_series(c,wid,se['series_uid'])
        image=lookup(c,'instances',wid,d.get('sop_instance_uid'))
        if image['series_id']!=lesion['series_id']: fail('病灶与切片不属于同一序列')
        coordinates=[d.get(k) for k in ('x_min','y_min','x_max','y_max')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in coordinates): fail('框坐标必须是有限数值')
        x1,y1,x2,y2=coordinates
        if not (0<=x1<x2<=image['width'] and 0<=y1<y2<=image['height']): fail('框坐标越界')
        source=lookup(c,'boxes',wid,d['source_box_id']) if d.get('source_box_id') else None
        return dict(series_id=image['series_id'],lesion_id=lesion['id'],image_id=image['id'],public_id=uuid_key(key),
                    x_min=x1,y_min=y1,x_max=x2,y_max=y2,source_box_id=source['id'] if source else None)
    fail('不支持的数据类别')

def encode(kind, r, maps):
    result={'version':r['version']}
    if kind=='patients': result.update(id=r['client_id'],patient_code=r['patient_code'],issuer=r['issuer'])
    elif kind=='studies': result.update(id=r['study_uid'],patient_id=maps['patients'][r['patient_id']]['client_id'],description=r['description'],date=r['study_date'].strftime('%Y%m%d') if r['study_date'] else '',accession_number=r['accession_number'],study_time=r['study_time'].strftime('%H%M%S.%f') if r['study_time'] else '')
    elif kind=='series': result.update(id=r['series_uid'],study_id=maps['studies'][r['study_id']]['study_uid'],description=r['description'],number=r['series_number'] if r['series_number'] is not None else '',orientation=r['plane'],modality=r['modality'])
    elif kind=='instances':
        result.update(id=r['sop_instance_uid'],series_id=maps['series'][r['series_id']]['series_uid'],width=r['width'],height=r['height'],order=r['sort_order'],instance_number=r['instance_number'],metadata={})
        for name,cols in [('position',('position_x','position_y','position_z')),('orientation',('row_cosine_x','row_cosine_y','row_cosine_z','column_cosine_x','column_cosine_y','column_cosine_z')),('pixel_spacing',('pixel_spacing_row','pixel_spacing_column'))]:
            result[name]=[r[x] for x in cols] if all(r[x] is not None for x in cols) else []
    elif kind=='diseases': result.update(id=r['code'],disease_code=r['code'],disease_name=r['name'],box_policy=r['box_policy'],overall_fields=r['overall_schema'],lesion_fields=r['lesion_schema'],target_keys=r['target_keys'],active=r['active'])
    elif kind in ('lesions','assessments'):
        se=maps['series'][r['series_id']];disease=maps['diseases'][r['disease_id']]
        result.update(id=r['public_id'] if kind=='lesions' else '|'.join([se['series_uid'],disease['code'],r['target_key']]),
            series_id=se['series_uid'],study_id=maps['studies'][se['study_id']]['study_uid'],disease_type_id=disease['code'],target_key=r['target_key'],attributes_json=r['attributes'])
        if kind=='lesions': result.update(color=r['color'],tissue_type=r['target_key'])
        else: result['status']=r['status']
    elif kind=='boxes':
        image=maps['instances'][r['image_id']]
        result.update(id=r['public_id'],lesion_instance_id=maps['lesions'][r['lesion_id']]['public_id'],sop_instance_uid=image['sop_instance_uid'],image_width=image['width'],image_height=image['height'],**{k:r[k] for k in ('x_min','y_min','x_max','y_max')})
        if r['source_box_id'] in maps['boxes']: result['source_box_id']=maps['boxes'][r['source_box_id']]['public_id']
    return result

def state(c,wid):
    maps={k:{r['id']:r for r in c.execute(scoped(k,wid)).mappings()} for k in KINDS}
    hidden_studies={pk for pk,r in maps['studies'].items() if r['deleted_at']}
    hidden_series={pk for pk,r in maps['series'].items() if r['deleted_at'] or r['study_id'] in hidden_studies}
    hidden_lesions={pk for pk,r in maps['lesions'].items() if r['deleted_at'] or r['series_id'] in hidden_series}
    result={k:[] for k in KINDS}
    for kind,rows in maps.items():
        for pk,r in rows.items():
            if kind=='studies' and pk in hidden_studies: continue
            if kind=='series' and pk in hidden_series: continue
            if kind in ('instances','assessments','lesions','boxes') and r['series_id'] in hidden_series: continue
            if kind=='lesions' and pk in hidden_lesions: continue
            if kind=='assessments' and r['deleted_at']: continue
            if kind=='boxes' and (r['deleted_at'] or r['lesion_id'] in hidden_lesions): continue
            result[kind].append(encode(kind,r,maps))
    result.update(groups=[],segmentations=[])
    result['_deleted']={k:[encode(k,r,maps) for r in maps[k].values() if r['deleted_at']] for k in ('assessments','lesions','boxes')}
    return result

@router.get('/{public_id}/state')
def get_state(public_id:str):
    try:
        with engine.begin() as c:
            ws=workspace(c,public_id)
            # Serialize initial snapshot against mutations in this space. Mutations
            # hold this lock only for their short transaction; versions are per row.
            c.execute(select(m.workspaces.c.id).where(m.workspaces.c.id==ws['id']).with_for_update()).first()
            return {'state':state(c,ws['id'])}
    except IntegrityError: fail('空间正在初始化，请重试',409)

def operator(value):
    from urllib.parse import unquote
    value=unquote(value) if isinstance(value,str) else value
    return limited(value.strip() if isinstance(value,str) else value,128,'操作人姓名或工号')

def audit(c,wid,actor,kind,key,action,before,after):
    def snapshot(row):
        return json.loads(json.dumps(dict(row),default=str,ensure_ascii=False)) if row is not None else None
    c.execute(m.change_logs.insert().values(workspace_id=wid,actor=actor,entity_type=kind,
        entity_key=key,action=action,before_value=snapshot(before),after_value=snapshot(after)))

@router.post('/{public_id}/changes')
def changes(public_id:str,payload:dict, x_operator: str | None = Header(default=None)):
    actor=operator(x_operator)
    check_payload(payload)
    operations=payload.get('operations')
    if not isinstance(operations,list) or len(operations)>2000: fail('每批最多 2000 条操作')
    try:
        with engine.begin() as c:
            ws=workspace(c,public_id);wid=ws['id']
            c.execute(select(m.workspaces.c.id).where(m.workspaces.c.id==wid).with_for_update()).first()
            output=[];seen=set()
            for op in operations:
                if not isinstance(op,dict): fail('操作格式错误')
                kind=op.get('kind');action=op.get('action','upsert');d=op.get('record',{})
                if kind not in KINDS or not isinstance(d,dict): fail('不支持的数据类别')
                key=limited(d.get('id'),512,'记录 ID')
                if (kind,key) in seen: fail('单批请求不可重复修改同一记录')
                seen.add((kind,key))
                expected=op.get('expected_version')
                if isinstance(expected,bool) or not isinstance(expected,int) or expected<0: fail('缺少有效记录版本')
                old=lookup(c,kind,wid,key,False,True)
                if (old is None and expected!=0) or (old is not None and old['version']!=expected): fail('此记录已被其他页面修改，请刷新后重试',409)
                t=m.TABLES[kind]
                if action=='delete':
                    if not old: fail('记录不存在',404)
                    if kind not in ('boxes','lesions','assessments'): fail('请使用移除检查或序列接口')
                    c.execute(update(t).where(t.c.id==old['id'],t.c.version==expected).values(deleted_at=stamp(),version=expected+1,updated_at=stamp()))
                    audit(c,wid,actor,kind,key,'delete',old,lookup(c,kind,wid,key))
                    output.append(dict(kind=kind,id=key,version=expected+1));continue
                if action!='upsert': fail('未知操作')
                v=values(c,kind,wid,d)
                if old:
                    # Existing image hierarchy is immutable; reimport cannot reparent it.
                    for fk in ('workspace_id','patient_id','study_id','series_id','disease_id','lesion_id','image_id'):
                        if fk in v and fk in old and v[fk]!=old[fk]: fail('不能改变现有记录的所属关系',409)
                    if kind in ('studies','series') and old['deleted_at']: fail('请先恢复已移除数据',409)
                    if 'deleted_at' in t.c: v['deleted_at']=None
                    result=c.execute(update(t).where(t.c.id==old['id'],t.c.version==expected).values(**v,version=expected+1,updated_at=stamp()))
                    if result.rowcount!=1: fail('记录版本冲突',409)
                else:
                    c.execute(t.insert().values(**v,version=1))
                audit(c,wid,actor,kind,key,'update' if old else 'create',old,lookup(c,kind,wid,key))
                output.append(dict(kind=kind,id=key,version=expected+1))
            c.execute(update(m.workspaces).where(m.workspaces.c.id==wid).values(updated_at=stamp()))
            return {'changes':output,'saved_at':stamp().isoformat()+'Z'}
    except IntegrityError: fail('记录已存在或违反关联约束，请刷新后重试',409)

@router.post('/{public_id}/visibility')
def visibility(public_id:str,payload:dict, x_operator: str | None = Header(default=None)):
    actor=operator(x_operator)
    kind=payload.get('kind')
    if kind not in ('studies','series'): fail('仅支持移除检查或序列')
    with engine.begin() as c:
        ws=workspace(c,public_id);wid=ws['id']
        c.execute(select(m.workspaces.c.id).where(m.workspaces.c.id==wid).with_for_update()).first()
        row=lookup(c,kind,wid,payload.get('id'),lock=True)
        if payload.get('expected_version')!=row['version']: fail('记录已改变，请刷新后重试',409)
        restored=payload.get('restore',False)
        if not isinstance(restored,bool): fail('restore 必须是布尔值')
        if kind=='series' and restored and by_id(c,'studies',wid,row['study_id'])['deleted_at']: fail('请先恢复所属检查',409)
        c.execute(update(m.TABLES[kind]).where(m.TABLES[kind].c.id==row['id']).values(
            deleted_at=None if restored else stamp(),version=row['version']+1,updated_at=stamp()))
        audit(c,wid,actor,kind,payload['id'],'restore' if restored else 'hide',row,lookup(c,kind,wid,payload['id']))
        return {'ok':True,'archive_id':json.dumps(dict(kind=kind,id=payload['id'],version=row['version']+1)),
                'message':'已恢复' if restored else '已移除，可撤销；影像索引和标注仍保留'}
@router.post('/{public_id}/reimport')
def reimport(public_id:str,payload:dict, x_operator: str | None = Header(default=None)):
    actor=operator(x_operator)
    uids=payload.get('series_uids')
    if not isinstance(uids,list) or len(uids)>2000 or any(not isinstance(x,str) for x in uids):
        fail('无效的序列列表')
    with engine.begin() as c:
        ws=workspace(c,public_id);wid=ws['id']
        c.execute(select(m.workspaces.c.id).where(m.workspaces.c.id==wid).with_for_update()).first()
        for key in set(uids):
            se=lookup(c,'series',wid,key,required=False,lock=True)
            if se is None: continue
            st=by_id(c,'studies',wid,se['study_id'])
            for t,row in ((m.studies,st),(m.series,se)):
                if row['deleted_at']:
                    c.execute(update(t).where(t.c.id==row['id']).values(deleted_at=None,version=row['version']+1,updated_at=stamp()))
                    audit(c,wid,actor,t.name,str(row['id']),'reimport_restore',row,c.execute(select(t).where(t.c.id==row['id'])).mappings().one())
        return {'state':state(c,wid)}
