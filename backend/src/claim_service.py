from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select
from .models import Machine,Claim,Inspection,Audit,ModelState

def obj(x):return {c.name:getattr(x,c.name) for c in x.__table__.columns}
def get(s,model,id):
    x=s.get(model,id)
    if not x:raise HTTPException(404,'记录不存在')
    return x
def audit(s,u,action,detail):s.add(Audit(actor=u['email'],action=action,detail=str(detail),at=datetime.now(timezone.utc).isoformat()))
def claim_view(s,c):
    d=obj(c);d['machine_serial']=s.get(Machine,c.machine_id).serial
    i=s.scalar(select(Inspection).where(Inspection.claim_id==c.id));d['inspection']=obj(i) if i else None
    return d
def current_epoch(s):
    st=s.get(ModelState,1)
    if not st:st=ModelState(id=1,epoch=1);s.add(st);s.flush()
    return st
def submit(s,data,u):
    m=get(s,Machine,data.machine_id)
    if data.hours_at_failure<m.hours:raise HTTPException(409,'故障工时不能小于机具最新台账工时')
    c=Claim(**data.model_dump(),historical=False,status='out_of_warranty' if data.hours_at_failure>m.warranty_hours else 'submitted',assessment_note='超出质保工时' if data.hours_at_failure>m.warranty_hours else '')
    m.hours=data.hours_at_failure;s.add(c);s.flush();audit(s,u,'claim_received',c.code);return claim_view(s,c)
def inspect(s,c,data,u):
    if c.status!='assessed':raise HTTPException(409,'仅完成风险分流的索赔可补拆检')
    i=s.scalar(select(Inspection).where(Inspection.claim_id==c.id))
    if not i:i=Inspection(claim_id=c.id,decision='pending',**data.model_dump());s.add(i)
    else:i.findings=data.findings;i.evidence_complete=data.evidence_complete
    audit(s,u,'inspection_updated',c.code);s.flush();return obj(i)
def save_review(s,c,data,u):
    if c.status!='assessed':raise HTTPException(409,'仅待裁决索赔可留存复核依据')
    if c.coverage!='manual_review':raise HTTPException(409,'该索赔未转人工复核，无需复核依据')
    c.review_basis=data.review_basis.strip()
    audit(s,u,'review_basis_saved',c.code);s.flush();return claim_view(s,c)
def adjudicate(s,claim_id,decision,u):
    c=s.scalar(select(Claim).where(Claim.id==claim_id).with_for_update().execution_options(populate_existing=True))
    if not c:raise HTTPException(404,'记录不存在')
    if c.status=='out_of_warranty':raise HTTPException(409,'机具故障工时已过保，不允许质保赔付')
    if c.status!='assessed':raise HTTPException(409,'索赔须完成风险分流，且不可重复裁决')
    if decision=='paid' and (c.score_epoch!=current_epoch(s).epoch or c.coverage is None):raise HTTPException(409,'评分缺覆盖依据或已过期，待重算完成后才能签赔')
    i=s.scalar(select(Inspection).where(Inspection.claim_id==c.id))
    if not i:raise HTTPException(409,'必须先记录拆检意见')
    if decision=='paid':
        if c.coverage=='manual_review':
            if not i.evidence_complete:raise HTTPException(409,'转人工复核索赔须拆检证据齐全才可签赔')
            if len((c.review_basis or '').strip())<8:raise HTTPException(409,'主管须写明复核依据后才可签赔')
        if c.risk is not None and c.risk>=.5 and not i.evidence_complete:raise HTTPException(409,'高争议风险索赔必须补齐拆检证据后才能赔付')
    c.status=decision;i.decision=decision;audit(s,u,'claim_adjudicated',f'{c.code}:{decision}');return claim_view(s,c)
def upgrade_model(s,note,u):
    st=current_epoch(s)
    st.epoch+=1;st.upgraded_at=datetime.now(timezone.utc).isoformat();st.note=(note or '').strip()
    stale=s.scalars(select(Claim).where(Claim.historical==False,Claim.status=='assessed',(Claim.score_epoch!=st.epoch)|(Claim.coverage.is_(None)))).all()
    for c in stale:c.status='queued'
    audit(s,u,'model_upgraded',f'epoch={st.epoch} 待裁决重算{len(stale)}单 {st.note}'.strip())
    s.flush();return st,[c.id for c in stale]
