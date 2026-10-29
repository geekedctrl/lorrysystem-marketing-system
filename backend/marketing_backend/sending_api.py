import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import user, scope
from .db import session
from .models import Approval, Delivery, DeliveryAttempt, EmailSuppression, PreparationRun, SenderConnection, now
from .sending import decrypt_secret, encrypt_secret, normalized_email, smtp_handoff, HandoffError

router = APIRouter(prefix="/workspaces/{wid}", tags=["Controlled email delivery"])

class Strict(BaseModel): model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
class SenderWrite(Strict):
    name: str = Field(min_length=2,max_length=120); from_email: str = Field(max_length=254); from_name: str = Field(min_length=2,max_length=120)
    host: str = Field(min_length=3,max_length=253,pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$")
    port: Literal[465,587]; security: Literal["TLS","STARTTLS"]; username: str = Field(min_length=1,max_length=254)
    password: SecretStr|None=None; enabled: bool=False
    @field_validator("from_email")
    @classmethod
    def email(cls,v): return normalized_email(v)
    @field_validator("name","from_name","username")
    @classmethod
    def line(cls,v):
        if re.search(r"[\x00-\x1f\x7f]",v): raise ValueError("Use a single line")
        return v
    @model_validator(mode="after")
    def pairing(self):
        if (self.security,self.port) not in (("TLS",465),("STARTTLS",587)): raise ValueError("Use TLS on 465 or STARTTLS on 587")
        return self
class CreateDelivery(Strict): approval_id: UUID; sender_id: UUID; idempotency_key: str = Field(min_length=8,max_length=120)
class ApproveSend(Strict): confirmed: Literal[True]
class RetryDelivery(Strict): confirmed: Literal[True]
class Suppress(Strict):
    email: str; reason: Literal["OPT_OUT","BOUNCE","DO_NOT_CONTACT"]
    @field_validator("email")
    @classmethod
    def email_address(cls,v): return normalized_email(v)

def sender_read(x):
    return {k:getattr(x,k) for k in ("id","name","from_email","from_name","host","port","security","username","enabled","verified_at","created_at")}
def delivery_read(x,db):
    attempts=list(db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==x.id).order_by(DeliveryAttempt.attempt_number)))
    return {"id":x.id,"approval_id":x.approval_id,"sender_id":x.sender_id,"status":x.status,"snapshot":x.snapshot,"requested_by":x.requested_by,"send_approved_by":x.send_approved_by,"send_approved_at":x.send_approved_at,"created_at":x.created_at,"attempts":[{"id":a.id,"number":a.attempt_number,"status":a.status,"message_id":a.message_id,"failure_code":a.failure_code,"created_at":a.created_at,"finished_at":a.finished_at} for a in attempts]}

@router.get("/senders")
def senders(wid:UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db); return [sender_read(x) for x in db.scalars(select(SenderConnection).where(SenderConnection.workspace_id==wid).order_by(SenderConnection.created_at))]
@router.post("/senders",status_code=201)
def create_sender(wid:UUID,data:SenderWrite,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"])
    if data.password is None: raise HTTPException(422,"Provide an SMTP password")
    x=SenderConnection(workspace_id=wid,**data.model_dump(exclude={"password"}),secret_ciphertext=encrypt_secret(data.password.get_secret_value(),wid)); db.add(x); db.commit(); return sender_read(x)
@router.put("/senders/{sid}")
def update_sender(wid:UUID,sid:UUID,data:SenderWrite,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]); x=db.scalar(select(SenderConnection).where(SenderConnection.workspace_id==wid,SenderConnection.id==sid).with_for_update())
    if not x: raise HTTPException(404,"Sender connection not found")
    if db.scalar(select(Delivery.id).where(Delivery.workspace_id==wid,Delivery.sender_id==sid,Delivery.status.in_(["QUEUED","SENDING"]))):
        raise HTTPException(409,"Sender connection is reserved by an active delivery")
    for k,v in data.model_dump(exclude={"password"}).items(): setattr(x,k,v)
    if data.password is not None: x.secret_ciphertext=encrypt_secret(data.password.get_secret_value(),wid)
    x.verified_at=None; db.commit(); return sender_read(x)
@router.post("/senders/{sid}/verify")
def verify_sender(wid:UUID,sid:UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN"]); x=db.scalar(select(SenderConnection).where(SenderConnection.workspace_id==wid,SenderConnection.id==sid).with_for_update())
    if not x: raise HTTPException(404,"Sender connection not found")
    try: smtp_handoff(x,decrypt_secret(x))
    except HandoffError as exc: x.verified_at=None; db.commit(); return {"verified":False,"failure_reason":exc.code}
    x.verified_at=now(); db.commit(); return {"verified":True,"verified_at":x.verified_at}

@router.post("/deliveries",status_code=201)
def create_delivery(wid:UUID,data:CreateDelivery,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"])
    existing=db.scalar(select(Delivery).where(Delivery.workspace_id==wid,Delivery.create_key==data.idempotency_key))
    if existing:
        if existing.approval_id!=data.approval_id: raise HTTPException(409,"Idempotency key belongs to another delivery")
        return delivery_read(existing,db)
    approval=db.scalar(select(Approval).where(Approval.workspace_id==wid,Approval.id==data.approval_id).with_for_update())
    sender=db.scalar(select(SenderConnection).where(SenderConnection.workspace_id==wid,SenderConnection.id==data.sender_id))
    if not approval or approval.status!="APPROVED": raise HTTPException(409,"An approved draft is required")
    if not sender or not sender.enabled or not sender.verified_at: raise HTTPException(409,"Use an enabled verified sender")
    draft=approval.snapshot.get("draft",{})
    try: recipient=normalized_email(draft.get("recipient", ""))
    except ValueError: raise HTTPException(409,"Approved draft has no valid recipient") from None
    if draft.get("channel")!="EMAIL": raise HTTPException(409,"Only approved email drafts can be delivered")
    if any(character in draft.get("subject","") for character in "\r\n"): raise HTTPException(409,"Approved subject must be a single line")
    if db.scalar(select(EmailSuppression.id).where(EmailSuppression.workspace_id==wid,EmailSuppression.email==recipient)): raise HTTPException(409,"Recipient is suppressed")
    run=db.scalar(select(PreparationRun).where(PreparationRun.workspace_id==wid,PreparationRun.id==approval.run_id))
    if not run or run.status!="APPROVED" or run.context_hash!=approval.snapshot.get("context_hash"): raise HTTPException(409,"Approved draft context is stale")
    snap={"recipient":recipient,"subject":draft["subject"],"body":draft["body"],"channel":"EMAIL","approval_version":approval.version,"approval_id":str(approval.id),"context_hash":run.context_hash}
    if run.snapshot.get("product_line"):
        from .product_lines import for_run,line_for
        from .pipeline import fingerprint
        from .stage_contracts import content_hash
        if line_for(db,wid,run.product_line_id).paused or fingerprint(for_run(db,run))!=run.context_hash:
            raise HTTPException(409,"Product-line approval context is stale")
        snap.update(product_line_id=str(run.product_line_id),asset_hash=content_hash(draft),asset_type=draft.get("asset_type","EMAIL_TEXT"))
    x=Delivery(workspace_id=wid,approval_id=approval.id,sender_id=sender.id,create_key=data.idempotency_key,snapshot=snap,requested_by=actor.id); db.add(x)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Delivery already exists for this approval") from None
    return delivery_read(x,db)

@router.get("/deliveries")
def deliveries(wid:UUID,approval_id:UUID|None=None,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db)
    query=select(Delivery).where(Delivery.workspace_id==wid)
    if approval_id: query=query.where(Delivery.approval_id==approval_id)
    return [delivery_read(x,db) for x in db.scalars(query.order_by(Delivery.created_at.desc()).limit(100))]

@router.post("/deliveries/{did}/approve-send",status_code=202)
def approve_send(wid:UUID,did:UUID,data:ApproveSend,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"]); x=db.scalar(select(Delivery).where(Delivery.workspace_id==wid,Delivery.id==did).with_for_update())
    if not x: raise HTTPException(404,"Delivery not found")
    from .approval_context import valid_delivery
    if not valid_delivery(db,x):raise HTTPException(409,"Approved product-line snapshot is stale")
    if x.status!="PENDING_SEND_APPROVAL":
        if x.send_approved_by: return delivery_read(x,db)
        raise HTTPException(409,"Delivery cannot be approved")
    x.status,x.send_approved_by,x.send_approved_at,x.updated_at="QUEUED",actor.id,now(),now()
    db.add(DeliveryAttempt(workspace_id=wid,delivery_id=x.id,attempt_number=1,status="READY",message_id=f"<{x.id}@pending>")); db.commit(); return delivery_read(x,db)
@router.post("/deliveries/{did}/retry",status_code=202)
def retry_delivery(wid:UUID,did:UUID,data:RetryDelivery,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"]); x=db.scalar(select(Delivery).where(Delivery.workspace_id==wid,Delivery.id==did).with_for_update())
    if not x: raise HTTPException(404,"Delivery not found")
    from .approval_context import valid_delivery
    if not valid_delivery(db,x):raise HTTPException(409,"Approved product-line snapshot is stale")
    attempts=list(db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==did).order_by(DeliveryAttempt.attempt_number)))
    if x.status!="FAILED" or not attempts or len(attempts)>=3: raise HTTPException(409,"Only known pre-handoff failures can be retried, up to three attempts")
    x.status,x.updated_at="QUEUED",now(); db.add(DeliveryAttempt(workspace_id=wid,delivery_id=x.id,attempt_number=len(attempts)+1,status="READY",message_id=attempts[0].message_id)); db.commit(); return delivery_read(x,db)
@router.get("/deliveries/{did}")
def get_delivery(wid:UUID,did:UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db); x=db.scalar(select(Delivery).where(Delivery.workspace_id==wid,Delivery.id==did))
    if not x: raise HTTPException(404,"Delivery not found")
    return delivery_read(x,db)
@router.post("/email-suppressions",status_code=201)
def suppress(wid:UUID,data:Suppress,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db,["ADMIN","OPERATOR"]); x=db.scalar(select(EmailSuppression).where(EmailSuppression.workspace_id==wid,EmailSuppression.email==data.email))
    if x: x.reason=data.reason
    else: x=EmailSuppression(workspace_id=wid,**data.model_dump()); db.add(x)
    db.commit(); return {"id":x.id,"email":x.email,"reason":x.reason}

@router.get("/email-suppressions")
def suppressions(wid:UUID,actor=Depends(user),db=Depends(session)):
    scope(wid,actor,db)
    return [{"id":x.id,"email":x.email,"reason":x.reason,"created_at":x.created_at} for x in db.scalars(select(EmailSuppression).where(EmailSuppression.workspace_id==wid).order_by(EmailSuppression.created_at.desc()).limit(100))]
