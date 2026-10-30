"""Line-aware snapshot verification at approval/outbox boundaries."""
from sqlalchemy import select,text
from .models import Approval,PreparationRun,Lead
from .product_lines import for_run,line_for
from .pipeline import fingerprint
from .stage_contracts import content_hash


def valid_delivery(db,delivery,require_send=False):
    approval=db.get(Approval,delivery.approval_id)
    run=db.get(PreparationRun,approval.run_id) if approval else None
    if not run:return False
    draft=approval.snapshot.get("draft",{})
    if (approval.status!="APPROVED" or run.status!="APPROVED" or not approval.decision.get("actor_id")
        or delivery.product_line_id!=run.product_line_id
        or delivery.channel!=draft.get("channel")
        or delivery.snapshot.get("approval_version")!=approval.version
        or delivery.snapshot.get("context_hash")!=run.context_hash
        or approval.snapshot.get("context_hash")!=run.context_hash):return False
    for field in ("recipient","subject","body","channel"):
        if delivery.snapshot.get(field)!=draft.get(field):return False
    if require_send and not (delivery.send_approved_by and delivery.send_approved_at):return False
    if not run.snapshot.get("product_line"):return True
    if require_send:
        db.execute(text("SELECT worker_lock_product_line(:wid,:lid)"),{"wid":run.workspace_id,"lid":run.product_line_id})
        db.scalar(select(Lead).where(Lead.workspace_id==run.workspace_id,Lead.id==run.lead_id).with_for_update())
    line=line_for(db,run.workspace_id,run.product_line_id)
    latest=db.scalar(select(PreparationRun.id).where(PreparationRun.workspace_id==run.workspace_id,
        PreparationRun.product_line_id==run.product_line_id,PreparationRun.lead_id==run.lead_id)
        .order_by(PreparationRun.created_at.desc(),PreparationRun.id.desc()).limit(1))
    draft=approval.snapshot.get("draft",{})
    if (line.paused or latest!=run.id or approval.status!="APPROVED" or run.status!="APPROVED"
        or not approval.decision.get("actor_id")
        or delivery.product_line_id!=run.product_line_id
        or delivery.snapshot.get("product_line_id")!=str(run.product_line_id)
        or delivery.snapshot.get("asset_hash")!=content_hash(draft)
        or delivery.snapshot.get("context_hash")!=run.context_hash
        or fingerprint(for_run(db,run))!=run.context_hash):return False
    for field in ("recipient","subject","body","channel"):
        if delivery.snapshot.get(field)!=draft.get(field):return False
    return bool(delivery.send_approved_by and delivery.send_approved_at) if require_send else True
