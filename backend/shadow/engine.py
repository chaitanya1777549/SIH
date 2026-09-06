"""
Shadow Block detection, constraint validation, and attachment engine.
Enforces railway structural constraints:
1. Exact Section Match: Candidate must be on the same block section.
2. Duration Window Fit: Candidate duration <= Primary block duration.
3. Deadline Satisfaction: Primary window must complete before candidate required_by.
4. Controller Approval Workflow: Attaches only on controller confirmation.
5. Audit Traceability: Appends to block_allocation_history with reason='shadow_block_attached'.
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from collections import defaultdict
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from backend.models import (
    Block,
    BlockRequest,
    BlockAllocationHistory,
    BlockSection,
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
)
from backend.schemas import (
    ShadowCandidateSchema,
    ShadowCheckResponseSchema,
    ShadowAttachRequestSchema,
    ShadowAttachResponseSchema,
    ShadowDiscardRequestSchema,
    ShadowDiscardResponseSchema,
)

logger = logging.getLogger("backend.shadow.engine")

def find_shadow_candidates_for_block(
    db: Session,
    block_id: UUID,
) -> ShadowCheckResponseSchema:
    """
    Evaluates an existing primary block against all pending requests and open defects
    on the exact same section to discover viable shadow block candidates.
    """
    primary_block = (
        db.query(Block)
        .options(
            joinedload(Block.block_section).joinedload(BlockSection.from_station),
            joinedload(Block.block_section).joinedload(BlockSection.to_station),
            joinedload(Block.block_request).joinedload(BlockRequest.tms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.smms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.tdms_defect),
        )
        .filter(Block.id == block_id, Block.status == "active")
        .first()
    )

    if not primary_block:
        raise HTTPException(status_code=404, detail=f"Active block '{block_id}' not found.")

    if primary_block.block_type == "shadow":
        raise HTTPException(status_code=400, detail="Cannot attach a shadow block to another shadow block.")

    sec = primary_block.block_section
    sec_id = primary_block.block_section_id
    primary_dur_min = int((primary_block.planned_end - primary_block.planned_start).total_seconds() // 60)
    primary_start = primary_block.planned_start
    primary_end = primary_block.planned_end

    primary_req = primary_block.block_request
    primary_defect = None
    if primary_req:
        primary_defect = primary_req.tms_defect or primary_req.smms_defect or primary_req.tdms_defect

    candidates: List[ShadowCandidateSchema] = []

    # 1. Search pending BlockRequests on the same section (excluding current primary block's request)
    pending_reqs = (
        db.query(BlockRequest)
        .options(
            joinedload(BlockRequest.tms_defect),
            joinedload(BlockRequest.smms_defect),
            joinedload(BlockRequest.tdms_defect),
        )
        .filter(
            BlockRequest.block_section_id == sec_id,
            BlockRequest.status == "pending",
            BlockRequest.id != primary_block.block_request_id,
        )
        .all()
    )

    for req in pending_reqs:
        defect = req.tms_defect or req.smms_defect or req.tdms_defect
        defect_id = defect.id if defect else req.id
        defect_code = defect.defect_code if defect else f"REQ-{str(req.id)[:6]}"
        defect_type = defect.defect_type if defect else "General Maintenance"

        # Check structural constraints
        cand = _evaluate_candidate_fit(
            candidate_type="block_request",
            candidate_id=req.id,
            block_request_id=req.id,
            defect_id=defect_id,
            source_system=req.source_system,
            defect_code=defect_code,
            defect_type=defect_type,
            criticality_score=req.criticality_score,
            duration_min=req.estimated_duration_min,
            required_by=req.required_by,
            primary_duration_min=primary_dur_min,
            primary_start=primary_start,
            primary_end=primary_end,
            detected_at=getattr(req, "created_at", None),
        )
        if cand:
            candidates.append(cand)

    # 2. Also search open eligible defects on the same section that haven't been requested yet
    req_tuples = db.query(
        BlockRequest.tms_defect_id,
        BlockRequest.smms_defect_id,
        BlockRequest.tdms_defect_id,
    ).all()
    existing_req_defect_ids = {
        d_id for row in req_tuples for d_id in row if d_id is not None
    }

    dept_models = [
        ("TMS", TMSDefect, TMSDefect.requires_track_block),
        ("SMMS", SMMSDefect, SMMSDefect.requires_signal_block),
        ("TDMS", TDMSDefect, TDMSDefect.requires_power_block),
    ]

    for dept_name, Model, block_flag in dept_models:
        open_defects = (
            db.query(Model)
            .filter(
                Model.block_section_id == sec_id,
                Model.status == "open",
                block_flag == True,
            )
            .all()
        )
        for d in open_defects:
            if d.id in existing_req_defect_ids:
                continue  # Already represented as a block_request

            cand = _evaluate_candidate_fit(
                candidate_type="defect",
                candidate_id=d.id,
                block_request_id=None,
                defect_id=d.id,
                source_system=dept_name,
                defect_code=d.defect_code,
                defect_type=d.defect_type,
                criticality_score=d.criticality_score,
                duration_min=d.estimated_duration_min,
                required_by=d.required_by,
                primary_duration_min=primary_dur_min,
                primary_start=primary_start,
                primary_end=primary_end,
                detected_at=getattr(d, "detected_at", None),
            )
            if cand:
                candidates.append(cand)

    # Sort candidates by criticality descending, then fit ratio descending
    candidates.sort(key=lambda c: (-c.criticality_score, -c.duration_fit_ratio))

    return ShadowCheckResponseSchema(
        primary_block_id=primary_block.id,
        block_section_id=sec_id,
        section_code=sec.section_code if sec else "",
        from_station_code=sec.from_station.station_code if sec and sec.from_station else None,
        to_station_code=sec.to_station.station_code if sec and sec.to_station else None,
        primary_start=primary_start,
        primary_end=primary_end,
        primary_duration_min=primary_dur_min,
        primary_source_system=primary_req.source_system if primary_req else None,
        primary_defect_code=primary_defect.defect_code if primary_defect else None,
        candidate_count=len(candidates),
        candidates=candidates,
    )

def _evaluate_candidate_fit(
    candidate_type: str,
    candidate_id: UUID,
    block_request_id: Optional[UUID],
    defect_id: UUID,
    source_system: str,
    defect_code: str,
    defect_type: str,
    criticality_score: int,
    duration_min: int,
    required_by: Optional[datetime],
    primary_duration_min: int,
    primary_start: datetime,
    primary_end: datetime,
    detected_at: Optional[datetime] = None,
) -> Optional[ShadowCandidateSchema]:
    """
    Verifies the candidate against hard structural constraints:
    1. Duration constraint: duration <= primary duration
    2. Deadline constraint: primary_end <= required_by
    """
    # Constraint 1: Duration fit
    if duration_min > primary_duration_min:
        return None

    # Constraint 2: Deadline satisfaction
    margin_hours: Optional[float] = None
    if required_by:
        req_by_utc = required_by if required_by.tzinfo else required_by.replace(tzinfo=timezone.utc)
        prim_end_utc = primary_end if primary_end.tzinfo else primary_end.replace(tzinfo=timezone.utc)
        
        if prim_end_utc > req_by_utc:
            return None  # Primary block completes after candidate deadline
            
        margin_hours = round((req_by_utc - prim_end_utc).total_seconds() / 3600, 1)

    fit_ratio = round(duration_min / primary_duration_min, 2)
    reason = (
        f"Fits within primary window ({duration_min}m <= {primary_duration_min}m) "
        f"on same section. Zero additional train delays."
    )

    return ShadowCandidateSchema(
        candidate_type=candidate_type,
        candidate_id=candidate_id,
        block_request_id=block_request_id,
        defect_id=defect_id,
        source_system=source_system,
        department=source_system,
        defect_code=defect_code,
        defect_type=defect_type,
        criticality_score=criticality_score,
        estimated_duration_min=duration_min,
        required_by=required_by,
        detected_at=detected_at,
        duration_fit_ratio=fit_ratio,
        margin_before_deadline_hours=margin_hours,
        recommendation_reason=reason,
    )

def find_all_corridor_shadow_opportunities(
    db: Session,
) -> List[ShadowCheckResponseSchema]:
    """
    Scans all active primary blocks across the corridor and returns
    those with one or more viable shadow block candidates.
    Optimized with batch loading to eliminate N+1 remote roundtrips.
    """
    active_primary_blocks = (
        db.query(Block)
        .options(
            joinedload(Block.block_section).joinedload(BlockSection.from_station),
            joinedload(Block.block_section).joinedload(BlockSection.to_station),
            joinedload(Block.block_request).joinedload(BlockRequest.tms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.smms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.tdms_defect),
        )
        .filter(Block.status == "active", Block.block_type == "primary")
        .order_by(Block.planned_start.asc())
        .all()
    )

    if not active_primary_blocks:
        return []

    sec_ids = {b.block_section_id for b in active_primary_blocks if b.block_section_id}

    # 1. Fetch pending BlockRequests on all relevant sections in ONE query
    pending_reqs_all = (
        db.query(BlockRequest)
        .options(
            joinedload(BlockRequest.tms_defect),
            joinedload(BlockRequest.smms_defect),
            joinedload(BlockRequest.tdms_defect),
        )
        .filter(
            BlockRequest.block_section_id.in_(sec_ids),
            BlockRequest.status == "pending",
        )
        .all()
    )
    pending_by_sec = defaultdict(list)
    for req in pending_reqs_all:
        pending_by_sec[req.block_section_id].append(req)

    # 2. Defect IDs already represented in any BlockRequest in ONE query
    req_tuples = db.query(
        BlockRequest.tms_defect_id,
        BlockRequest.smms_defect_id,
        BlockRequest.tdms_defect_id,
    ).all()
    existing_req_defect_ids = {
        d_id for row in req_tuples for d_id in row if d_id is not None
    }

    # 3. Fetch open eligible defects across all 3 departments in 3 bulk queries
    open_defects_by_sec = defaultdict(list)

    open_tms = (
        db.query(TMSDefect)
        .filter(
            TMSDefect.block_section_id.in_(sec_ids),
            TMSDefect.status == "open",
            TMSDefect.requires_track_block == True,
        )
        .all()
    )
    for d in open_tms:
        if d.id not in existing_req_defect_ids:
            open_defects_by_sec[d.block_section_id].append(("TMS", d))

    open_smms = (
        db.query(SMMSDefect)
        .filter(
            SMMSDefect.block_section_id.in_(sec_ids),
            SMMSDefect.status == "open",
            SMMSDefect.requires_signal_block == True,
        )
        .all()
    )
    for d in open_smms:
        if d.id not in existing_req_defect_ids:
            open_defects_by_sec[d.block_section_id].append(("SMMS", d))

    open_tdms = (
        db.query(TDMSDefect)
        .filter(
            TDMSDefect.block_section_id.in_(sec_ids),
            TDMSDefect.status == "open",
            TDMSDefect.requires_power_block == True,
        )
        .all()
    )
    for d in open_tdms:
        if d.id not in existing_req_defect_ids:
            open_defects_by_sec[d.block_section_id].append(("TDMS", d))

    opportunities: List[ShadowCheckResponseSchema] = []

    # 4. Evaluate in memory for each active primary block
    for blk in active_primary_blocks:
        sec = blk.block_section
        sec_id = blk.block_section_id
        primary_dur_min = int((blk.planned_end - blk.planned_start).total_seconds() // 60)
        primary_start = blk.planned_start
        primary_end = blk.planned_end

        primary_req = blk.block_request
        primary_defect = None
        if primary_req:
            primary_defect = primary_req.tms_defect or primary_req.smms_defect or primary_req.tdms_defect

        candidates: List[ShadowCandidateSchema] = []

        # A. Pending BlockRequests on same section
        for req in pending_by_sec.get(sec_id, []):
            if req.id == blk.block_request_id:
                continue
            defect = req.tms_defect or req.smms_defect or req.tdms_defect
            defect_id = defect.id if defect else req.id
            defect_code = defect.defect_code if defect else f"REQ-{str(req.id)[:6]}"
            defect_type = defect.defect_type if defect else "General Maintenance"

            cand = _evaluate_candidate_fit(
                candidate_type="block_request",
                candidate_id=req.id,
                block_request_id=req.id,
                defect_id=defect_id,
                source_system=req.source_system,
                defect_code=defect_code,
                defect_type=defect_type,
                criticality_score=req.criticality_score,
                duration_min=req.estimated_duration_min,
                required_by=req.required_by,
                primary_duration_min=primary_dur_min,
                primary_start=primary_start,
                primary_end=primary_end,
                detected_at=getattr(req, "created_at", None),
            )
            if cand:
                candidates.append(cand)

        # B. Open unrequested defects on same section
        for dept_name, d in open_defects_by_sec.get(sec_id, []):
            cand = _evaluate_candidate_fit(
                candidate_type="defect",
                candidate_id=d.id,
                block_request_id=None,
                defect_id=d.id,
                source_system=dept_name,
                defect_code=d.defect_code,
                defect_type=d.defect_type,
                criticality_score=d.criticality_score,
                duration_min=d.estimated_duration_min,
                required_by=d.required_by,
                primary_duration_min=primary_dur_min,
                primary_start=primary_start,
                primary_end=primary_end,
                detected_at=getattr(d, "detected_at", None),
            )
            if cand:
                candidates.append(cand)

        if candidates:
            candidates.sort(key=lambda c: (-c.criticality_score, -c.duration_fit_ratio))
            opportunities.append(
                ShadowCheckResponseSchema(
                    primary_block_id=blk.id,
                    block_section_id=sec_id,
                    section_code=sec.section_code if sec else "",
                    from_station_code=sec.from_station.station_code if sec and sec.from_station else None,
                    to_station_code=sec.to_station.station_code if sec and sec.to_station else None,
                    primary_start=primary_start,
                    primary_end=primary_end,
                    primary_duration_min=primary_dur_min,
                    primary_source_system=primary_req.source_system if primary_req else None,
                    primary_defect_code=primary_defect.defect_code if primary_defect else None,
                    candidate_count=len(candidates),
                    candidates=candidates,
                )
            )

    return opportunities

def attach_shadow_block(
    db: Session,
    payload: ShadowAttachRequestSchema,
) -> ShadowAttachResponseSchema:
    """
    Executes the controller approval action to attach a shadow block to an existing primary block.
    Writes child block to blocks with block_type='shadow', records audit history,
    updates request/defect statuses to 'allocated', and produces department notification.
    """
    primary_block = (
        db.query(Block)
        .options(
            joinedload(Block.block_section),
            joinedload(Block.block_request),
        )
        .filter(Block.id == payload.primary_block_id, Block.status == "active")
        .first()
    )

    if not primary_block:
        raise HTTPException(status_code=404, detail=f"Primary block '{payload.primary_block_id}' not found.")

    if primary_block.block_type != "primary":
        raise HTTPException(status_code=400, detail="Target block must be a primary block, not a shadow block.")

    primary_dur_min = int((primary_block.planned_end - primary_block.planned_start).total_seconds() // 60)
    now_utc = datetime.now(timezone.utc)

    # 1. Resolve or create the BlockRequest
    req: Optional[BlockRequest] = None
    defect_obj = None
    dept_input = (payload.department or getattr(payload, "source_system", None) or "").upper()

    if payload.block_request_id:
        req = (
            db.query(BlockRequest)
            .options(
                joinedload(BlockRequest.tms_defect),
                joinedload(BlockRequest.smms_defect),
                joinedload(BlockRequest.tdms_defect),
            )
            .filter(BlockRequest.id == payload.block_request_id)
            .first()
        )
        if not req:
            raise HTTPException(status_code=404, detail=f"BlockRequest '{payload.block_request_id}' not found.")
        if req.status != "pending":
            raise HTTPException(status_code=400, detail=f"BlockRequest status is '{req.status}', must be 'pending'.")
        dept_str = req.source_system
        defect_obj = req.tms_defect or req.smms_defect or req.tdms_defect

    elif payload.defect_id:
        dept_str = dept_input
        if dept_str == "TMS":
            defect_obj = db.query(TMSDefect).filter(TMSDefect.id == payload.defect_id).first()
        elif dept_str == "SMMS":
            defect_obj = db.query(SMMSDefect).filter(SMMSDefect.id == payload.defect_id).first()
        elif dept_str == "TDMS":
            defect_obj = db.query(TDMSDefect).filter(TDMSDefect.id == payload.defect_id).first()
        else:
            # Auto-detect department across all three departments
            defect_obj = db.query(TMSDefect).filter(TMSDefect.id == payload.defect_id).first()
            if defect_obj:
                dept_str = "TMS"
            else:
                defect_obj = db.query(SMMSDefect).filter(SMMSDefect.id == payload.defect_id).first()
                if defect_obj:
                    dept_str = "SMMS"
                else:
                    defect_obj = db.query(TDMSDefect).filter(TDMSDefect.id == payload.defect_id).first()
                    if defect_obj:
                        dept_str = "TDMS"

        if not defect_obj:
            raise HTTPException(status_code=404, detail=f"Defect '{payload.defect_id}' not found.")
        if defect_obj.status != "open":
            raise HTTPException(status_code=400, detail=f"Defect status is '{defect_obj.status}', must be 'open'.")

        # Create BlockRequest snapshot
        req = BlockRequest(
            id=uuid.uuid4(),
            source_system=dept_str,
            tms_defect_id=defect_obj.id if dept_str == "TMS" else None,
            smms_defect_id=defect_obj.id if dept_str == "SMMS" else None,
            tdms_defect_id=defect_obj.id if dept_str == "TDMS" else None,
            block_section_id=defect_obj.block_section_id,
            criticality_score=defect_obj.criticality_score,
            required_by=defect_obj.required_by,
            estimated_duration_min=defect_obj.estimated_duration_min,
            requires_power_block=(dept_str == "TDMS"),
            requires_signal_block=(dept_str == "SMMS"),
            status="pending",
        )
        db.add(req)
        db.flush()
    else:
        raise HTTPException(
            status_code=400,
            detail="Either block_request_id or defect_id must be specified."
        )

    # 2. Strict Constraint Checks
    if req.block_section_id != primary_block.block_section_id:
        raise HTTPException(
            status_code=400,
            detail="Section mismatch: Shadow block must be on the exact same block section as the primary block."
        )

    if req.estimated_duration_min > primary_dur_min:
        raise HTTPException(
            status_code=400,
            detail=f"Duration violation: Candidate duration ({req.estimated_duration_min}m) exceeds primary window ({primary_dur_min}m)."
        )

    if req.required_by:
        req_by_utc = req.required_by if req.required_by.tzinfo else req.required_by.replace(tzinfo=timezone.utc)
        prim_end_utc = primary_block.planned_end if primary_block.planned_end.tzinfo else primary_block.planned_end.replace(tzinfo=timezone.utc)
        if prim_end_utc > req_by_utc:
            raise HTTPException(
                status_code=400,
                detail=f"Deadline violation: Primary block end ({prim_end_utc}) exceeds candidate deadline ({req_by_utc})."
            )

    # 3. Create Child Shadow Block
    shadow_start = primary_block.planned_start
    shadow_end = shadow_start + timedelta(minutes=req.estimated_duration_min)
    defect_code = defect_obj.defect_code if defect_obj else f"REQ-{str(req.id)[:6]}"
    sec_code = primary_block.block_section.section_code if primary_block.block_section else ""

    shadow_block = Block(
        id=uuid.uuid4(),
        block_request_id=req.id,
        block_section_id=primary_block.block_section_id,
        planned_start=shadow_start,
        planned_end=shadow_end,
        status="active",
        block_type="shadow",
        parent_block_id=primary_block.id,
        optimization_run_at=now_utc,
        created_at=now_utc,
    )
    db.add(shadow_block)
    db.flush()

    # 4. Insert Audit History Record
    history = BlockAllocationHistory(
        id=uuid.uuid4(),
        block_id=shadow_block.id,
        block_request_id=req.id,
        block_section_id=primary_block.block_section_id,
        previous_start=None,
        previous_end=None,
        new_start=shadow_start,
        new_end=shadow_end,
        reason="shadow_block_attached",
        changed_at=now_utc,
    )
    db.add(history)

    # 5. Update Statuses
    req.status = "allocated"

    if dept_str == "TMS" and req.tms_defect_id:
        db.query(TMSDefect).filter(TMSDefect.id == req.tms_defect_id).update({"status": "allocated"})
    elif dept_str == "SMMS" and req.smms_defect_id:
        db.query(SMMSDefect).filter(SMMSDefect.id == req.smms_defect_id).update({"status": "allocated"})
    elif dept_str == "TDMS" and req.tdms_defect_id:
        db.query(TDMSDefect).filter(TDMSDefect.id == req.tdms_defect_id).update({"status": "allocated"})

    db.commit()

    # 6. Green Approval Notification for Originating Department
    notification_payload = {
        "type": "SHADOW_BLOCK_APPROVED",
        "department": dept_str,
        "defect_code": defect_code,
        "color": "green",
        "title": f"Shadow Block Approved ({dept_str})",
        "message": (
            f"COA Controller approved Shadow Block for {defect_code} on section {sec_code} "
            f"piggybacking on primary block #{str(primary_block.id)[:8]} "
            f"({shadow_start.strftime('%d-%b %H:%M')} to {shadow_end.strftime('%H:%M')}). "
            f"Corridor availability maximized with 0 additional train delay."
        ),
        "timestamp": now_utc.isoformat(),
    }

    return ShadowAttachResponseSchema(
        status="APPROVED",
        shadow_block_id=shadow_block.id,
        parent_block_id=primary_block.id,
        block_section_id=primary_block.block_section_id,
        section_code=sec_code,
        planned_start=shadow_start,
        planned_end=shadow_end,
        duration_min=req.estimated_duration_min,
        source_system=dept_str,
        defect_code=defect_code,
        message="Shadow block successfully attached to primary block.",
        notification=notification_payload,
    )

def discard_shadow_proposal(
    db: Session,
    payload: ShadowDiscardRequestSchema,
) -> ShadowDiscardResponseSchema:
    """
    Handles controller discarding of a shadow block proposal.
    Produces a red decline notification for the originating department.
    """
    now_utc = datetime.now(timezone.utc)
    dept = (payload.department or getattr(payload, "source_system", None) or "").upper()
    if not dept and payload.defect_id:
        if db.query(TMSDefect).filter(TMSDefect.id == payload.defect_id).first():
            dept = "TMS"
        elif db.query(SMMSDefect).filter(SMMSDefect.id == payload.defect_id).first():
            dept = "SMMS"
        elif db.query(TDMSDefect).filter(TDMSDefect.id == payload.defect_id).first():
            dept = "TDMS"
    dept = dept or "TMS"

    notification_payload = {
        "type": "SHADOW_BLOCK_DECLINED",
        "department": dept,
        "color": "red",
        "title": f"Shadow Block Declined ({dept})",
        "message": f"COA Controller discarded shadow block proposal: {payload.reason}.",
        "timestamp": now_utc.isoformat(),
    }

    return ShadowDiscardResponseSchema(
        status="DISCARDED",
        message="Shadow block proposal was discarded by controller.",
        notification=notification_payload,
    )
