"""
Dynamic Train Delay Propagation & Intelligent Re-Optimization Engine.

Handles:
1. Propagation of station-reported delays downstream along a train's corridor path.
2. Temporal conflict detection between updated train forecasts and active maintenance blocks.
3. Intelligent conflict resolution decision matrix:
   - High Criticality (>= threshold or critical severity): Divert conflicting train to preserve safety-critical block.
   - Normal/Low Criticality (< threshold): Revoke maintenance block, notify department (RED), and immediately:
     a) Attempt to attach as an immediate Shadow Block on an existing block on the same section.
     b) If no shadow block, search for the next available free gap before the defect deadline.
     c) Defer to pending if no slot is available before deadline.
"""
import uuid
import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from backend.models import (
    Train,
    Station,
    BlockSection,
    TrainSchedule,
    Block,
    BlockRequest,
    BlockAllocationHistory,
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
)
from backend.optimizer.gap_calculator import compute_section_free_gaps
from backend.schemas import (
    SectionForecastUpdate,
    TrainDelayUpdateResponseSchema,
    ConflictResolutionDetailSchema,
    DepartmentNotificationSchema,
    ReOptimizeResponseSchema,
)

logger = logging.getLogger("backend.reoptimizer")

# In-memory audit notification store for real-time frontend streaming
_NOTIFICATIONS: List[Dict[str, Any]] = []

def add_notification(
    department: str,
    notif_type: str,
    title: str,
    message: str,
    defect_code: Optional[str] = None,
    section_code: Optional[str] = None,
    action_taken: str = "PROCESSED",
) -> Dict[str, Any]:
    """Appends a new notification to the corridor feed."""
    notif = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc),
        "department": department,
        "type": notif_type,
        "title": title,
        "message": message,
        "defect_code": defect_code,
        "section_code": section_code,
        "action_taken": action_taken,
    }
    _NOTIFICATIONS.insert(0, notif)
    # Keep last 500 notifications
    if len(_NOTIFICATIONS) > 500:
        _NOTIFICATIONS.pop()
    return notif

def get_all_notifications(
    department: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieves notifications filtered by department if specified."""
    if department:
        dept_upper = department.upper()
        return [n for n in _NOTIFICATIONS if n["department"].upper() in (dept_upper, "ALL", "COA")][:limit]
    return _NOTIFICATIONS[:limit]

def clear_notifications() -> None:
    """Clears stored notifications (useful for tests)."""
    _NOTIFICATIONS.clear()


def propagate_train_delay(
    db: Session,
    train_number: str,
    service_date: date,
    station_code: str,
    delay_minutes: int,
) -> TrainDelayUpdateResponseSchema:
    """
    Applies reported delay at a station and propagates it downstream along
    the train's scheduled journey on the corridor.
    """
    logger.info(
        f"Propagating delay: Train {train_number}, Date {service_date}, "
        f"Station {station_code}, Delay +{delay_minutes}min"
    )

    train = db.query(Train).filter(Train.train_number == train_number).first()
    if not train:
        raise HTTPException(status_code=404, detail=f"Train '{train_number}' not found")

    station = db.query(Station).filter(Station.station_code == station_code.upper()).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{station_code}' not found")

    # Fetch all train schedules on service_date sorted chronologically
    schedules = (
        db.query(TrainSchedule)
        .options(
            joinedload(TrainSchedule.block_section).joinedload(BlockSection.from_station),
            joinedload(TrainSchedule.block_section).joinedload(BlockSection.to_station),
        )
        .filter(
            TrainSchedule.train_id == train.id,
            TrainSchedule.service_date == service_date,
        )
        .order_by(TrainSchedule.scheduled_entry.asc())
        .all()
    )

    if not schedules:
        raise HTTPException(
            status_code=404,
            detail=f"No timetable found for Train '{train_number}' on {service_date}",
        )

    # Locate the starting schedule index at or downstream from station_code
    target_station_id = station.id
    start_index: Optional[int] = None

    for idx, s in enumerate(schedules):
        sec = s.block_section
        if sec.from_station_id == target_station_id or sec.to_station_id == target_station_id:
            start_index = idx
            break

    if start_index is None:
        raise HTTPException(
            status_code=400,
            detail=f"Train '{train_number}' does not traverse station '{station_code}' on {service_date}",
        )

    updated_sections: List[SectionForecastUpdate] = []
    delta = timedelta(minutes=delay_minutes)

    for idx in range(start_index, len(schedules)):
        sched = schedules[idx]
        sched.delay_minutes = delay_minutes
        sched.forecast_entry = sched.scheduled_entry + delta
        sched.forecast_exit = sched.scheduled_exit + delta
        sched.updated_at = datetime.now(timezone.utc)

        sec = sched.block_section
        updated_sections.append(
            SectionForecastUpdate(
                section_code=sec.section_code,
                from_station=sec.from_station.station_code,
                to_station=sec.to_station.station_code,
                scheduled_entry=sched.scheduled_entry,
                scheduled_exit=sched.scheduled_exit,
                forecast_entry=sched.forecast_entry,
                forecast_exit=sched.forecast_exit,
                delay_minutes=sched.delay_minutes,
                status=sched.status,
            )
        )

    db.commit()

    add_notification(
        department="COA",
        notif_type="AMBER",
        title=f"TRAIN DELAY PROPAGATED: Train {train_number}",
        message=f"Train {train_number} delayed by {delay_minutes}m at {station_code}. Updated forecast across {len(updated_sections)} downstream sections.",
        section_code=updated_sections[0].section_code if updated_sections else None,
        action_taken="DELAY_PROPAGATED",
    )

    return TrainDelayUpdateResponseSchema(
        status="success",
        train_number=train_number,
        service_date=service_date,
        reported_station=station_code.upper(),
        delay_minutes=delay_minutes,
        updated_sections_count=len(updated_sections),
        updated_sections=updated_sections,
    )


def detect_conflicts(
    db: Session,
    service_date: date,
    section_id: Optional[UUID] = None,
    safety_buffer_min: int = 10,
) -> List[Tuple[TrainSchedule, Block]]:
    """
    Detects temporal overlaps between active blocks and train forecast occupancies
    (including safety buffer) on the corridor for the given date.
    """
    day_start = datetime.combine(service_date, time.min).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(service_date + timedelta(days=1), time.max).replace(tzinfo=timezone.utc)

    block_query = (
        db.query(Block)
        .options(
            joinedload(Block.block_section),
            joinedload(Block.block_request).joinedload(BlockRequest.tms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.smms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.tdms_defect),
        )
        .filter(
            Block.status == "active",
            Block.planned_start < day_end,
            Block.planned_end > day_start,
        )
    )
    if section_id:
        block_query = block_query.filter(Block.block_section_id == section_id)
    active_blocks = block_query.all()

    sched_query = (
        db.query(TrainSchedule)
        .options(
            joinedload(TrainSchedule.train),
            joinedload(TrainSchedule.block_section),
        )
        .filter(
            TrainSchedule.service_date == service_date,
            TrainSchedule.status.in_(["scheduled", "running"]),  # Skip already diverted/cancelled
        )
    )
    if section_id:
        sched_query = sched_query.filter(TrainSchedule.block_section_id == section_id)
    schedules = sched_query.all()

    buffer_delta = timedelta(minutes=safety_buffer_min)
    conflicts: List[Tuple[TrainSchedule, Block]] = []

    for block in active_blocks:
        b_sec_id = block.block_section_id
        for sched in schedules:
            if sched.block_section_id != b_sec_id:
                continue

            train_start = sched.forecast_entry - buffer_delta
            train_end = sched.forecast_exit + buffer_delta

            # Overlap check
            if train_start < block.planned_end and train_end > block.planned_start:
                conflicts.append((sched, block))

    return conflicts


def resolve_conflicts_and_reoptimize(
    db: Session,
    service_date: date,
    section_code: Optional[str] = None,
    criticality_threshold: int = 60,
    safety_buffer_min: int = 10,
) -> ReOptimizeResponseSchema:
    """
    Executes the intelligent conflict resolution decision matrix:
    - High-Criticality Block: Train is DIVERTED, block preserved.
    - Routine/Low-Criticality Block: Block REVOKED; attempts immediate Shadow Block
      or Free Gap rescheduling before deadline.
    """
    target_section_id: Optional[UUID] = None
    if section_code:
        sec = db.query(BlockSection).filter(BlockSection.section_code == section_code).first()
        if not sec:
            raise HTTPException(status_code=404, detail=f"Block section '{section_code}' not found")
        target_section_id = sec.id

    conflicts = detect_conflicts(
        db,
        service_date=service_date,
        section_id=target_section_id,
        safety_buffer_min=safety_buffer_min,
    )

    details: List[ConflictResolutionDetailSchema] = []
    generated_notifications: List[DepartmentNotificationSchema] = []
    diverted_count = 0
    revoked_count = 0
    rescheduled_count = 0

    # Group conflicting train schedules by block
    conflicts_by_block: Dict[UUID, Tuple[Block, List[TrainSchedule]]] = {}
    for sched, block in conflicts:
        if block.id not in conflicts_by_block:
            conflicts_by_block[block.id] = (block, [])
        conflicts_by_block[block.id][1].append(sched)

    for block_id, (block, conflicting_scheds) in conflicts_by_block.items():
        req = block.block_request
        sec = block.block_section
        primary_train = conflicting_scheds[0].train

        defect = req.tms_defect or req.smms_defect or req.tdms_defect
        dept = req.source_system
        defect_code = defect.defect_code if defect else f"REQ-{str(req.id)[:8]}"
        severity = getattr(defect, "severity", "medium") if defect else "medium"
        crit_score = req.criticality_score

        prev_start = block.planned_start
        prev_end = block.planned_end
        est_duration = req.estimated_duration_min if req else int((prev_end - prev_start).total_seconds() // 60)
        req_deadline = req.required_by if req else None

        is_emergency = (
            getattr(req, "is_emergency", False)
            or block.block_type == "emergency"
            or dept == "EMERGENCY"
            or (req and req.source_system == "EMERGENCY")
        )

        # -------------------------------------------------------------------------
        # EMERGENCY BLOCK CHECK:
        # Rule: Emergency blocks are NEVER checked for shadow blocks!
        # Safety possession is non-negotiable; block preserved, train halted/diverted.
        # -------------------------------------------------------------------------
        if is_emergency:
            for sched in conflicting_scheds:
                sched.status = "diverted"
                sched.updated_at = datetime.now(timezone.utc)
                diverted_count += 1
                t = sched.train

                notif_urgent = add_notification(
                    department="COA",
                    notif_type="BLUE",
                    title=f"URGENT DIRECTIVE: EMERGENCY BLOCK ACTIVE — DIVERT OR HALT TRAIN {t.train_number} on {sec.section_code}",
                    message=(
                        f"EMERGENCY BLOCK DIRECTIVE: Train {t.train_number} delayed into active EMERGENCY safety block "
                        f"({block.planned_start.strftime('%H:%M')} - {block.planned_end.strftime('%H:%M')}) on {sec.section_code}. "
                        f"Emergency blocks are never checked for shadow blocks or deferred. "
                        f"Block PRESERVED. COA DIRECTIVE: DIVERT Train {t.train_number} via adjacent track or "
                        f"HALT at upstream station loop line."
                    ),
                    defect_code=defect_code,
                    section_code=sec.section_code,
                    action_taken="EMERGENCY_TRAIN_DIVERT_OR_HALT",
                )
                generated_notifications.append(DepartmentNotificationSchema(**notif_urgent))

                details.append(
                    ConflictResolutionDetailSchema(
                        conflict_type="train_vs_block",
                        section_code=sec.section_code,
                        train_number=t.train_number,
                        train_forecast_entry=sched.forecast_entry,
                        train_forecast_exit=sched.forecast_exit,
                        block_id=block.id,
                        block_planned_start=block.planned_start,
                        block_planned_end=block.planned_end,
                        defect_code=defect_code,
                        defect_department=dept,
                        criticality_score=crit_score,
                        severity=severity,
                        decision="train_divert_or_halt",
                        rescheduled_slot=None,
                        notes=(
                            f"Active Emergency Block on {sec.section_code}. Emergency blocks are never checked for shadow blocks. "
                            f"Block preserved; COA notified to DIVERT or HALT Train {t.train_number}."
                        ),
                    )
                )
            continue

        # -------------------------------------------------------------------------
        # STAGE 1: Check for viable SHADOW BLOCK piggyback before defect deadline
        # (Only for routine / planned maintenance blocks; never for emergency blocks)
        # -------------------------------------------------------------------------
        rescheduled = False
        rescheduled_info: Optional[Dict[str, Any]] = None

        candidate_parents = (
            db.query(Block)
            .join(BlockRequest, Block.block_request_id == BlockRequest.id)
            .filter(
                Block.block_section_id == sec.id,
                Block.status == "active",
                Block.block_type == "primary",
                BlockRequest.is_emergency == False,
                Block.id != block.id,
                Block.planned_start >= block.planned_start,
            )
            .order_by(Block.planned_start.asc())
            .all()
        )

        for parent in candidate_parents:
            parent_duration = int((parent.planned_end - parent.planned_start).total_seconds() // 60)
            if parent_duration >= est_duration:
                # Must complete before defect deadline
                if req_deadline and parent.planned_end > req_deadline:
                    continue

                # Viable shadow block found before deadline!
                # Cancel original block slot so the delayed train can pass
                block.status = "cancelled"
                db.flush()

                shadow_end = parent.planned_start + timedelta(minutes=est_duration)
                new_shadow = Block(
                    block_request_id=req.id if req else None,
                    block_section_id=sec.id,
                    planned_start=parent.planned_start,
                    planned_end=shadow_end,
                    status="active",
                    block_type="shadow",
                    parent_block_id=parent.id,
                )
                db.add(new_shadow)
                db.flush()

                shadow_hist = BlockAllocationHistory(
                    block_id=new_shadow.id,
                    block_request_id=req.id if req else None,
                    block_section_id=sec.id,
                    previous_start=prev_start,
                    previous_end=prev_end,
                    new_start=new_shadow.planned_start,
                    new_end=new_shadow.planned_end,
                    reason="shadow_block_attached_due_to_train_delay",
                )
                db.add(shadow_hist)

                if req:
                    req.status = "allocated"
                if defect:
                    defect.status = "allocated"

                rescheduled_count += 1
                rescheduled = True
                rescheduled_info = {
                    "type": "shadow",
                    "block_id": str(new_shadow.id),
                    "parent_block_id": str(parent.id),
                    "planned_start": new_shadow.planned_start.isoformat(),
                    "planned_end": new_shadow.planned_end.isoformat(),
                }

                notif_green = add_notification(
                    department=dept,
                    notif_type="GREEN",
                    title=f"RESCHEDULED AS SHADOW BLOCK: {defect_code}",
                    message=(
                        f"Delayed trains detected into block window on {sec.section_code}. "
                        f"Defect {defect_code} successfully piggybacked as Shadow Block "
                        f"({new_shadow.planned_start.strftime('%H:%M')} - {new_shadow.planned_end.strftime('%H:%M')}) "
                        f"before deadline {req_deadline.strftime('%H:%M') if req_deadline else 'N/A'}. "
                        f"Original track slot released for trains."
                    ),
                    defect_code=defect_code,
                    section_code=sec.section_code,
                    action_taken="SHADOW_RESCHEDULED",
                )
                generated_notifications.append(DepartmentNotificationSchema(**notif_green))

                for sched in conflicting_scheds:
                    details.append(
                        ConflictResolutionDetailSchema(
                            conflict_type="train_vs_block",
                            section_code=sec.section_code,
                            train_number=sched.train.train_number,
                            train_forecast_entry=sched.forecast_entry,
                            train_forecast_exit=sched.forecast_exit,
                            block_id=block.id,
                            block_planned_start=prev_start,
                            block_planned_end=prev_end,
                            defect_code=defect_code,
                            defect_department=dept,
                            criticality_score=crit_score,
                            severity=severity,
                            decision="block_rescheduled_shadow",
                            rescheduled_slot=rescheduled_info,
                            notes=(
                                f"Train {sched.train.train_number} delayed into block window. Defect {defect_code} "
                                f"reallocated as shadow block before deadline; original track cleared for train."
                            ),
                        )
                    )
                break

        # -------------------------------------------------------------------------
        # STAGE 2: If no shadow block, check for viable FREE GAP before defect deadline
        # -------------------------------------------------------------------------
        if not rescheduled:
            horizon_start = datetime.combine(service_date, time.min).replace(tzinfo=timezone.utc)
            horizon_end = horizon_start + timedelta(days=3)

            train_rows = (
                db.query(TrainSchedule)
                .filter(
                    TrainSchedule.block_section_id == sec.id,
                    TrainSchedule.service_date >= service_date,
                    TrainSchedule.service_date <= (service_date + timedelta(days=3)),
                    TrainSchedule.status.in_(["scheduled", "running"]),
                )
                .all()
            )
            train_moves = [(t.forecast_entry, t.forecast_exit) for t in train_rows]

            other_blocks = (
                db.query(Block)
                .filter(
                    Block.block_section_id == sec.id,
                    Block.status == "active",
                    Block.id != block.id,
                )
                .all()
            )
            block_moves = [(b.planned_start, b.planned_end) for b in other_blocks]

            free_gaps = compute_section_free_gaps(
                section_id=sec.id,
                horizon_start=horizon_start,
                horizon_end=horizon_end,
                train_movements=train_moves,
                existing_blocks=block_moves,
                safety_buffer_min=safety_buffer_min,
            )

            for gap in free_gaps:
                if gap.end_dt <= prev_end:
                    continue

                if gap.duration_min >= est_duration:
                    slot_start = gap.start_dt
                    slot_end = slot_start + timedelta(minutes=est_duration)

                    # Must complete before defect deadline
                    if req_deadline and slot_end > req_deadline:
                        continue

                    # Viable free gap found before deadline!
                    block.status = "cancelled"
                    db.flush()

                    new_primary = Block(
                        block_request_id=req.id if req else None,
                        block_section_id=sec.id,
                        planned_start=slot_start,
                        planned_end=slot_end,
                        status="active",
                        block_type="primary",
                    )
                    db.add(new_primary)
                    db.flush()

                    gap_hist = BlockAllocationHistory(
                        block_id=new_primary.id,
                        block_request_id=req.id if req else None,
                        block_section_id=sec.id,
                        previous_start=prev_start,
                        previous_end=prev_end,
                        new_start=new_primary.planned_start,
                        new_end=new_primary.planned_end,
                        reason="free_gap_reallocated_due_to_train_delay",
                    )
                    db.add(gap_hist)

                    if req:
                        req.status = "allocated"
                    if defect:
                        defect.status = "allocated"

                    rescheduled_count += 1
                    rescheduled = True
                    rescheduled_info = {
                        "type": "gap",
                        "block_id": str(new_primary.id),
                        "planned_start": new_primary.planned_start.isoformat(),
                        "planned_end": new_primary.planned_end.isoformat(),
                    }

                    notif_green = add_notification(
                        department=dept,
                        notif_type="GREEN",
                        title=f"RESCHEDULED TO NEW GAP: {defect_code}",
                        message=(
                            f"Delayed trains detected into block window on {sec.section_code}. "
                            f"Defect {defect_code} successfully rescheduled into next free gap "
                            f"({new_primary.planned_start.strftime('%Y-%m-%d %H:%M')} - {new_primary.planned_end.strftime('%H:%M')}) "
                            f"before deadline {req_deadline.strftime('%H:%M') if req_deadline else 'N/A'}. "
                            f"Original slot released for trains."
                        ),
                        defect_code=defect_code,
                        section_code=sec.section_code,
                        action_taken="GAP_RESCHEDULED",
                    )
                    generated_notifications.append(DepartmentNotificationSchema(**notif_green))

                    for sched in conflicting_scheds:
                        details.append(
                            ConflictResolutionDetailSchema(
                                conflict_type="train_vs_block",
                                section_code=sec.section_code,
                                train_number=sched.train.train_number,
                                train_forecast_entry=sched.forecast_entry,
                                train_forecast_exit=sched.forecast_exit,
                                block_id=block.id,
                                block_planned_start=prev_start,
                                block_planned_end=prev_end,
                                defect_code=defect_code,
                                defect_department=dept,
                                criticality_score=crit_score,
                                severity=severity,
                                decision="block_rescheduled_gap",
                                rescheduled_slot=rescheduled_info,
                                notes=(
                                    f"Train {sched.train.train_number} delayed into block window. Defect {defect_code} "
                                    f"reallocated to available free gap before deadline; original track cleared for train."
                                ),
                            )
                        )
                    break

        # -------------------------------------------------------------------------
        # STAGE 3: Neither shadow block nor free gap possible before deadline:
        # Check criticality threshold (> 60)
        # -------------------------------------------------------------------------
        if not rescheduled:
            if crit_score >= criticality_threshold or severity in ("critical", "high"):
                # Criticality > 60: Defect cannot be moved without safety violation.
                # PRESERVE BLOCK. Notify COA with urgent directive to DIVERT or HALT every conflicting train!
                for sched in conflicting_scheds:
                    sched.status = "diverted"
                    sched.updated_at = datetime.now(timezone.utc)
                    diverted_count += 1
                    t = sched.train

                    notif_urgent = add_notification(
                        department="COA",
                        notif_type="BLUE",
                        title=f"URGENT DIRECTIVE: DIVERT OR HALT TRAIN {t.train_number} on {sec.section_code}",
                        message=(
                            f"CRITICAL DEFECT DIRECTIVE: Train {t.train_number} delayed into active safety block "
                            f"({block.planned_start.strftime('%H:%M')} - {block.planned_end.strftime('%H:%M')}) on {sec.section_code}. "
                            f"Defect {defect_code} is CRITICAL (Score: {crit_score} >= {criticality_threshold}, Severity: '{severity}') "
                            f"with NO alternative shadow block or free gap available before safety deadline "
                            f"({req_deadline.strftime('%H:%M') if req_deadline else 'immediate'}). "
                            f"Block PRESERVED. COA DIRECTIVE: DIVERT Train {t.train_number} via adjacent track or "
                            f"HALT at upstream station loop line."
                        ),
                        defect_code=defect_code,
                        section_code=sec.section_code,
                        action_taken="TRAIN_DIVERT_OR_HALT_DIRECTIVE",
                    )
                    generated_notifications.append(DepartmentNotificationSchema(**notif_urgent))

                    details.append(
                        ConflictResolutionDetailSchema(
                            conflict_type="train_vs_block",
                            section_code=sec.section_code,
                            train_number=t.train_number,
                            train_forecast_entry=sched.forecast_entry,
                            train_forecast_exit=sched.forecast_exit,
                            block_id=block.id,
                            block_planned_start=block.planned_start,
                            block_planned_end=block.planned_end,
                            defect_code=defect_code,
                            defect_department=dept,
                            criticality_score=crit_score,
                            severity=severity,
                            decision="train_divert_or_halt",
                            rescheduled_slot=None,
                            notes=(
                                f"Safety Critical Block (Score {crit_score} >= {criticality_threshold}). Neither shadow block nor gap available "
                                f"before deadline. Block preserved; COA notified to DIVERT or HALT Train {t.train_number}."
                            ),
                        )
                    )
            else:
                # Criticality <= 60 (Routine/Low): Revoke routine block & defer to pending review
                revoked_count += 1
                block.status = "cancelled"
                db.flush()

                if req:
                    req.status = "pending"
                if defect:
                    defect.status = "open"

                for sched in conflicting_scheds:
                    t = sched.train
                    notif_amber = add_notification(
                        department=dept,
                        notif_type="AMBER",
                        title=f"ROUTINE BLOCK REVOKED: {defect_code}",
                        message=(
                            f"Routine block ({defect_code}, score: {crit_score} <= {criticality_threshold}) on {sec.section_code} "
                            f"was REVOKED due to delay of Train {t.train_number}. "
                            f"No alternative shadow or gap slot before deadline; deferred to pending."
                        ),
                        defect_code=defect_code,
                        section_code=sec.section_code,
                        action_taken="DEFERRED_TO_PENDING",
                    )
                    generated_notifications.append(DepartmentNotificationSchema(**notif_amber))

                    details.append(
                        ConflictResolutionDetailSchema(
                            conflict_type="train_vs_block",
                            section_code=sec.section_code,
                            train_number=t.train_number,
                            train_forecast_entry=sched.forecast_entry,
                            train_forecast_exit=sched.forecast_exit,
                            block_id=block.id,
                            block_planned_start=prev_start,
                            block_planned_end=prev_end,
                            defect_code=defect_code,
                            defect_department=dept,
                            criticality_score=crit_score,
                            severity=severity,
                            decision="block_revoked_and_deferred",
                            rescheduled_slot=None,
                            notes=(
                                f"Routine defect (Score {crit_score} <= {criticality_threshold}). No alternative shadow or gap found before "
                                f"deadline; block revoked and deferred to pending review to allow delayed Train {t.train_number} to proceed."
                            ),
                        )
                    )

    db.commit()

    return ReOptimizeResponseSchema(
        status="success",
        service_date=service_date,
        conflicts_detected=len(conflicts),
        trains_diverted_count=diverted_count,
        blocks_revoked_count=revoked_count,
        blocks_rescheduled_count=rescheduled_count,
        details=details,
        notifications=generated_notifications,
    )


def delay_and_reoptimize(
    db: Session,
    train_number: str,
    service_date: date,
    station_code: str,
    delay_minutes: int,
    criticality_threshold: int = 60,
) -> Dict[str, Any]:
    """
    Unified one-click controller workflow:
    1. Propagate train delay from station downstream.
    2. Re-optimize corridor conflicts dynamically.
    """
    delay_res = propagate_train_delay(
        db=db,
        train_number=train_number,
        service_date=service_date,
        station_code=station_code,
        delay_minutes=delay_minutes,
    )

    reopt_res = resolve_conflicts_and_reoptimize(
        db=db,
        service_date=service_date,
        criticality_threshold=criticality_threshold,
    )

    return {
        "status": "success",
        "delay_update": delay_res,
        "reoptimization": reopt_res,
    }
