"""Study submission, completeness validation, and review workflow."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from backend import models as m
from backend.auth import require_user, require_reviewer

router=APIRouter(prefix='/api/workspaces',dependencies=[Depends(require_user)])
engine=None
BUILTINS={'ACL_INJURY','PCL_INJURY','MCL_INJURY','LCL_INJURY','PATELLAR_LIGAMENT_INJURY',
 'PATELLAR_RETINACULUM_INJURY','QUADRICEPS_TENDON_INJURY','POPLITEUS_TENDON_INJURY',
 'MENISCUS_INJURY','CARTILAGE_INJURY','HOFFA_FAT_PAD_ABNORMALITY','SYNOVIAL_ABNORMALITY',
 'JOINT_EFFUSION','BONE_INJURY','SUBCHONDRAL_INJURY'}

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)

def workspace(c,public_id):
    row=c.execute(select(m.workspaces).where(m.workspaces.c.public_id==public_id)).mappings().first()
    if not row: raise HTTPException(404,'标注空间不存在，请先打开标注页面')
    return row

def study(c,wid,study_uid):
    row=c.execute(select(m.studies).where(m.studies.c.workspace_id==wid,m.studies.c.study_uid==study_uid,m.studies.c.deleted_at.is_(None))).mappings().first()
    if not row: raise HTTPException(404,'检查不存在')
    return row

def empty(value): return value is None or value=='' or (isinstance(value,list) and not [x for x in value if x!=''])

def missing_fields(disease,fields,values):
    result=[]
    for field in fields or []:
        hidden=any(values.get(key)==expected for key,expected in (field.get('hide_when') or {}).items())
        required=disease['code'] in BUILTINS or field.get('required')
        if not hidden and required and empty(values.get(field.get('field_code'))):
            result.append(field.get('field_name') or field.get('field_code'))
    return result

def completeness(c,wid,st):
    series=c.execute(select(m.series).where(m.series.c.study_id==st['id'],m.series.c.deleted_at.is_(None)).order_by(m.series.c.id)).mappings().all()
    issues=[]
    diseases={r['id']:r for r in c.execute(select(m.diseases).where(m.diseases.c.workspace_id==wid,m.diseases.c.active.is_(True))).mappings()}
    annotated_count=0
    for se in series:
        assessments=c.execute(select(m.assessments).where(m.assessments.c.series_id==se['id'],m.assessments.c.deleted_at.is_(None))).mappings().all()
        lesions=c.execute(select(m.lesions).where(m.lesions.c.series_id==se['id'],m.lesions.c.deleted_at.is_(None))).mappings().all()
        boxes=c.execute(select(m.boxes).where(m.boxes.c.series_id==se['id'],m.boxes.c.deleted_at.is_(None))).mappings().all()
        boxed={b['lesion_id'] for b in boxes};active_lesions=[l for l in lesions if l['id'] in boxed]
        label=se['description'] or se['series_uid']
        # Extra scout/localizer sequences are allowed. A sequence becomes part of
        # the submission once any assessment or boxed lesion exists on it.
        if not assessments and not active_lesions: continue
        annotated_count+=1
        for a in assessments:
            d=diseases.get(a['disease_id'])
            if not d: continue
            missing=missing_fields(d,d['overall_schema'],a['attributes'] or {})
            if missing: issues.append(f'序列“{label}”的{d["name"]}整体属性缺少：'+ '、'.join(missing))
            if d['box_policy']=='REQUIRED' and not any(l['disease_id']==d['id'] and l['target_key']==a['target_key'] for l in active_lesions):
                issues.append(f'序列“{label}”的{d["name"]}缺少病灶框')
        for lesion in active_lesions:
            d=diseases.get(lesion['disease_id'])
            if not d: continue
            missing=missing_fields(d,d['lesion_schema'],lesion['attributes'] or {})
            if missing: issues.append(f'序列“{label}”的{d["name"]}局部属性缺少：'+ '、'.join(missing))
            if d['overall_schema'] and not any(a['disease_id']==d['id'] and a['target_key']==lesion['target_key'] for a in assessments):
                issues.append(f'序列“{label}”的{d["name"]}缺少整体评价')
    if annotated_count<3:
        issues.insert(0,f'至少需要完成 3 个序列的标注，当前已开始标注 {annotated_count} 个（检查共包含 {len(series)} 个序列）')
    return issues

def encoded_submission(row):
    return {k:(v.isoformat()+'Z' if isinstance(v,datetime) else v) for k,v in dict(row).items() if k not in ('workspace_id','study_id','submitter_user_id','reviewer_user_id')}

def submission_snapshot(c,study_id):
    result={}
    series_rows=c.execute(select(m.series).where(
        m.series.c.study_id==study_id,m.series.c.deleted_at.is_(None))).mappings().all()
    disease_rows=c.execute(select(m.diseases)).mappings().all()
    diseases={row['id']:row for row in disease_rows}
    for se in series_rows:
        series_label=f'{se["series_number"] or "?"} · {se["description"] or se["series_uid"]}'
        image_rows=c.execute(select(m.images.c.id,m.images.c.sop_instance_uid).where(
            m.images.c.series_id==se['id']).order_by(m.images.c.sort_order,m.images.c.id)).mappings().all()
        slice_numbers={row['id']:index+1 for index,row in enumerate(image_rows)}
        for row in c.execute(select(m.assessments).where(
            m.assessments.c.series_id==se['id'],m.assessments.c.deleted_at.is_(None))).mappings():
            disease=diseases.get(row['disease_id'])
            result[f'assessment:{row["id"]}']={
                'kind':'assessment','label':f'{series_label} · {disease["name"] if disease else "整体评价"}',
                'series_uid':se['series_uid'],'disease_code':disease['code'] if disease else None,
                'value':row['attributes'] or {}}
        lesions=c.execute(select(m.lesions).where(
            m.lesions.c.series_id==se['id'],m.lesions.c.deleted_at.is_(None))).mappings().all()
        lesion_map={row['id']:row for row in lesions}
        boxes=c.execute(select(m.boxes,m.images.c.instance_number,m.images.c.sop_instance_uid).join(
            m.images,m.boxes.c.image_id==m.images.c.id).where(
            m.boxes.c.series_id==se['id'],m.boxes.c.deleted_at.is_(None)).order_by(
            m.images.c.sort_order,m.images.c.id,m.boxes.c.id)).mappings().all()
        boxes_by_lesion={}
        for box in boxes: boxes_by_lesion.setdefault(box['lesion_id'],[]).append(box)
        for lesion in lesions:
            disease=diseases.get(lesion['disease_id'])
            anchor=(boxes_by_lesion.get(lesion['id']) or [None])[0]
            slice_number=slice_numbers.get(anchor['image_id']) if anchor else None
            result[f'lesion:{lesion["public_id"]}']={
                'kind':'lesion','label':f'{series_label} · {disease["name"] if disease else "病灶"} · 病灶属性'+
                    (f' · 第 {slice_number} 个切片' if slice_number else ''),
                'series_uid':se['series_uid'],'disease_code':disease['code'] if disease else None,
                'lesion_id':lesion['public_id'],
                'box_id':anchor['public_id'] if anchor else None,
                'sop_instance_uid':anchor['sop_instance_uid'] if anchor else None,
                'slice_index':slice_number,
                'value':lesion['attributes'] or {}}
        for box in boxes:
            lesion=lesion_map.get(box['lesion_id'])
            disease=diseases.get(lesion['disease_id']) if lesion else None
            result[f'box:{box["public_id"]}']={
                'kind':'box','label':f'{series_label} · {disease["name"] if disease else "病灶"} · 第 {slice_numbers.get(box["image_id"],"?")} 个切片',
                'series_uid':se['series_uid'],'disease_code':disease['code'] if disease else None,
                'lesion_id':lesion['public_id'] if lesion else None,'box_id':box['public_id'],
                'sop_instance_uid':box['sop_instance_uid'],'slice_index':slice_numbers.get(box['image_id']),
                'value':[round(float(box[key]),2) for key in ('x_min','y_min','x_max','y_max')]}
    return result

def snapshot_changes(previous,current):
    if current is None: return {'available':False,'reason':'当前提交没有标注快照'}
    if previous is None: return {'available':True,'first':True,'added':[],'modified':[],'deleted':[]}
    added=[current[key] for key in current.keys()-previous.keys()]
    deleted=[previous[key] for key in previous.keys()-current.keys()]
    modified=[current[key] for key in current.keys()&previous.keys()
        if current[key].get('value')!=previous[key].get('value')]
    order=lambda item:item.get('label','')
    return {'available':True,'first':False,'added':sorted(added,key=order),
        'modified':sorted(modified,key=order),'deleted':sorted(deleted,key=order)}

def append_history(c,submission_id,user_id,action,status,revision,reason=None,snapshot=None):
    c.execute(m.submission_review_history.insert().values(
        submission_id=submission_id,actor_user_id=user_id,action=action,
        status=status,revision=revision,reason=reason,snapshot=snapshot))

def review_history(c,submission_id):
    rows=c.execute(select(m.submission_review_history,m.users.c.username.label('actor_username'),
        m.users.c.display_name.label('actor_name')).join(
        m.users,m.submission_review_history.c.actor_user_id==m.users.c.id).where(
        m.submission_review_history.c.submission_id==submission_id).order_by(
        m.submission_review_history.c.id)).mappings()
    return [{k:(v.isoformat()+'Z' if isinstance(v,datetime) else v) for k,v in dict(row).items()
        if k not in ('submission_id','actor_user_id','snapshot')} for row in rows]

def revision_changes(c,submission_id):
    rows=c.execute(select(m.submission_review_history.c.action,m.submission_review_history.c.snapshot).where(
        m.submission_review_history.c.submission_id==submission_id).order_by(
        m.submission_review_history.c.id.desc())).mappings().all()
    # Revision differences are submission-to-submission only. Review decisions
    # and intermediate annotation saves are workflow/audit events, not versions.
    versions=[row for row in rows if row['action'] in ('SUBMIT','RESUBMIT')]
    if not versions: return {'available':False,'reason':'暂无提交快照'}
    current=versions[0]['snapshot']
    previous=versions[1]['snapshot'] if len(versions)>1 else None
    if len(versions)>1 and previous is None:
        return {'available':False,'reason':'上一次提交发生在差异记录功能启用之前'}
    return snapshot_changes(previous,current)

def submission_rows(c,wid,user):
    stmt=select(m.submissions,m.studies.c.study_uid,m.studies.c.description.label('study_description'),
        m.studies.c.source_patient_folder,m.studies.c.source_study_folder,
        m.patients.c.patient_code.label('patient_code'),m.patients.c.client_id.label('patient_id'),
        m.users.c.username.label('submitter_username'),m.users.c.display_name.label('submitter_name'))\
        .join(m.studies,m.submissions.c.study_id==m.studies.c.id)\
        .join(m.patients,m.studies.c.patient_id==m.patients.c.id)\
        .join(m.users,m.submissions.c.submitter_user_id==m.users.c.id)\
        .where(m.submissions.c.workspace_id==wid).order_by(m.submissions.c.updated_at.desc())
    if user['role']=='ANNOTATOR': stmt=stmt.where(m.submissions.c.submitter_user_id==user['id'])
    result=[]
    for row in c.execute(stmt).mappings():
        item=encoded_submission(row)
        reviewer=c.execute(select(m.users.c.username,m.users.c.display_name).where(m.users.c.id==row['reviewer_user_id'])).mappings().first() if row['reviewer_user_id'] else None
        item['reviewer']=dict(reviewer) if reviewer else None
        item['history']=review_history(c,row['id'])
        item['revision_changes']=revision_changes(c,row['id']);result.append(item)
    return result

@router.get('/{public_id}/submissions')
def list_submissions(public_id:str,user=Depends(require_user)):
    with engine.connect() as c:
        ws=workspace(c,public_id);return {'submissions':submission_rows(c,ws['id'],user)}

@router.post('/{public_id}/studies/{study_uid}/submit')
def submit_study(public_id:str,study_uid:str,user=Depends(require_user)):
    if user['role']!='ANNOTATOR': raise HTTPException(403,'只有普通用户可以提交标注')
    with engine.begin() as c:
        ws=workspace(c,public_id);st=study(c,ws['id'],study_uid)
        issues=completeness(c,ws['id'],st)
        if issues: raise HTTPException(422,{'message':'提交前检查未通过','issues':issues})
        old=c.execute(select(m.submissions).where(m.submissions.c.workspace_id==ws['id'],m.submissions.c.study_id==st['id']).with_for_update()).mappings().first()
        values=dict(submitter_user_id=user['id'],reviewer_user_id=None,status='SUBMITTED',rejection_reason=None,submitted_at=now(),reviewed_at=None)
        if old:
            if old['status']=='SUBMITTED': raise HTTPException(409,'该检查正在等待审核，请勿重复提交')
            values['revision']=old['revision']+1
            c.execute(update(m.submissions).where(m.submissions.c.id==old['id']).values(**values,updated_at=now()))
            submission_id=old['id']
            action='RESUBMIT'
        else:
            submission_id=c.execute(m.submissions.insert().values(workspace_id=ws['id'],study_id=st['id'],revision=1,**values)).inserted_primary_key[0]
            action='SUBMIT'
        row=c.execute(select(m.submissions).where(m.submissions.c.id==submission_id)).mappings().one()
        append_history(c,submission_id,user['id'],action,'SUBMITTED',row['revision'],
            snapshot=submission_snapshot(c,st['id']))
    return {'submission':encoded_submission(row)}

@router.post('/{public_id}/submissions/{submission_id}/review')
def review(public_id:str,submission_id:int,payload:dict,user=Depends(require_reviewer)):
    action=payload.get('action');reason=payload.get('reason','')
    if action not in ('approve','reject'): raise HTTPException(422,'审核操作必须为 approve 或 reject')
    if action=='reject' and (not isinstance(reason,str) or not reason.strip()): raise HTTPException(422,'驳回时必须填写理由')
    if not isinstance(reason,str) or len(reason)>1000: raise HTTPException(422,'驳回理由最多 1000 字')
    with engine.begin() as c:
        ws=workspace(c,public_id)
        row=c.execute(select(m.submissions).where(m.submissions.c.id==submission_id,m.submissions.c.workspace_id==ws['id']).with_for_update()).mappings().first()
        if not row: raise HTTPException(404,'提交记录不存在')
        if row['status']!='SUBMITTED': raise HTTPException(409,'该提交已处理或已被重新提交')
        st=c.execute(select(m.studies).where(m.studies.c.id==row['study_id'])).mappings().one()
        if action=='approve':
            issues=completeness(c,ws['id'],st)
            if issues: raise HTTPException(409,{'message':'标注在审核前发生变化，已不完整','issues':issues})
        c.execute(update(m.submissions).where(m.submissions.c.id==submission_id).values(status='APPROVED' if action=='approve' else 'REJECTED',
            reviewer_user_id=user['id'],rejection_reason=None if action=='approve' else reason.strip(),reviewed_at=now(),updated_at=now()))
        result=c.execute(select(m.submissions).where(m.submissions.c.id==submission_id)).mappings().one()
        append_history(c,submission_id,user['id'],action.upper(),result['status'],result['revision'],
            None if action=='approve' else reason.strip())
    return {'submission':encoded_submission(result)}
