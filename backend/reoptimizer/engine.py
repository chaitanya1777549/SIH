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
    criticality_threshold: int = 70,
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

    # Keep track of already processed blocks in this pass
    processed_blocks = set()

    for sched, block in conflicts:
        if block.id in processed_blocks:
            continue
        processed_blocks.add(block.id)

        req = block.block_request
        sec = block.block_section
        train = sched.train

        defect = req.tms_defect or req.smms_defect or req.tdms_defect
        dept = req.source_system
        defect_code = defect.defect_code if defect else f"REQ-{str(req.id)[:8]}"
        severity = getattr(defect, "severity", "medium") if defect else "medium"
        crit_score = req.criticality_score

        # Determine criticality classification
        is_high_criticality = (crit_score >= criticality_threshold) or (severity == "critical")

        if is_high_criticality:
            # === BRANCH 1: HIGH CRITICALITY -> DIVERT TRAIN ===
            sched.status = "diverted"
            sched.updated_at = datetime.now(timezone.utc)
            diverted_count += 1

            notif = add_notification(
                department=dept,
                notif_type="BLUE",
                title=f"TRAIN DIVERTED: Train {train.train_number} on {sec.section_code}",
                message=(
                    f"Train {train.train_number} DIVERTED on {sec.section_code} due to High-Criticality "
                    f"safety block ({defect_code}, score: {crit_score}). "
                    f"Maintenance window {block.planned_start.strftime('%H:%M')} - "
                    f"{block.planned_end.strftime('%H:%M')} PRESERVED."
                ),
                defect_code=defect_code,
                section_code=sec.section_code,
                action_taken="TRAIN_DIVERTED",
            )
            generated_notifications.append(DepartmentNotificationSchema(**notif))

            details.append(
                ConflictResolutionDetailSchema(
                    conflict_type="train_vs_block",
                    section_code=sec.section_code,
                    train_number=train.train_number,
                    train_forecast_entry=sched.forecast_entry,
                    train_forecast_exit=sched.forecast_exit,
                    block_id=block.id,
                    block_planned_start=block.planned_start,
                    block_planned_end=block.planned_end,
                    defect_code=defect_code,
                    defect_department=dept,
                    criticality_score=crit_score,
                    severity=severity,
                    decision="train_diverted",
                    rescheduled_slot=None,
                    notes=(
                        f"Safety Critical Block (Score {crit_score}, Severity '{severity}'). "
                        f"Block preserved; Train {train.train_number} diverted via alternate routing."
                    ),
                )
            )

        else:
            # === BRANCH 2: NORMAL/LOW CRITICALITY -> REVOKE BLOCK & RESCHEDULE ===
            revoked_count += 1
            prev_start = block.planned_start
            prev_end = block.planned_end

            # Revoke current block
            block.status = "cancelled"
            db.flush()

            # Record revocation in audit history
            revoke_hist = BlockAllocationHistory(
                block_id=block.id,
                block_request_id=req.id,
                block_section_id=sec.id,
                previous_start=prev_start,
                previous_end=prev_end,
                new_start=None,
                new_end=None,
                reason="reoptimized_due_to_delay",
            )
            db.add(revoke_hist)
            db.flush()

            # Send immediate RED notification to department
            notif_red = add_notification(
                department=dept,
                notif_type="RED",
                title=f"BLOCK REVOKED: {defect_code} on {sec.section_code}",
                message=(
                    f"Routine maintenance block ({defect_code}, score: {crit_score}) on {sec.section_code} "
                    f"was REVOKED due to delay of Train {train.train_number}. System seeking immediate rescheduling."
                ),
                defect_code=defect_code,
                section_code=sec.section_code,
                action_taken="BLOCK_REVOKED",
            )
            generated_notifications.append(DepartmentNotificationSchema(**notif_red))

            # Attempt immediate rescheduling
            rescheduled = False
            rescheduled_info: Optional[Dict[str, Any]] = None

            # --- Attempt A: Immediate Shadow Block Piggyback ---
            candidate_parents = (
                db.query(Block)
                .filter(
                    Block.block_section_id == sec.id,
                    Block.status == "active",
                    Block.block_type == "primary",
                    Block.id != block.id,
                )
                .order_by(Block.planned_start.asc())
                .all()
            )

            for parent in candidate_parents:
                parent_duration = int((parent.planned_end - parent.planned_start).total_seconds() // 60)
                if parent_duration >= req.estimated_duration_min:
                    # Check deadline
                    if req.required_by and parent.planned_end > req.required_by:
                        continue

                    # Viable shadow block found!
                    shadow_end = parent.planned_start + timedelta(minutes=req.estimated_duration_min)
                    new_shadow = Block(
                        block_request_id=req.id,
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
                        block_request_id=req.id,
                        block_section_id=sec.id,
                        previous_start=prev_start,
                        previous_end=prev_end,
                        new_start=new_shadow.planned_start,
                        new_end=new_shadow.planned_end,
                        reason="shadow_block_attached",
                    )
                    db.add(shadow_hist)

                    # Update status
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
                            f"Defect {defect_code} successfully rescheduled as Shadow Block on {sec.section_code} "
                            f"({new_shadow.planned_start.strftime('%H:%M')} - {new_shadow.planned_end.strftime('%H:%M')}) "
                            f"piggybacking on primary block {str(parent.id)[:8]}."
                        ),
                        defect_code=defect_code,
                        section_code=sec.section_code,
                        action_taken="SHADOW_RESCHEDULED",
                    )
                    generated_notifications.append(DepartmentNotificationSchema(**notif_green))
                    break

            # --- Attempt B: Next Available Free Gap ---
            if not rescheduled:
                horizon_start = datetime.combine(service_date, time.min).replace(tzinfo=timezone.utc)
                horizon_end = horizon_start + timedelta(days=3)  # Look up to 72 hours ahead

                # Fetch train occupancies on this section
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

                # Fetch other active blocks on this section
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

                # Find earliest viable gap
                for gap in free_gaps:
                    # Skip gaps that end before the original block was supposed to end
                    if gap.end_dt <= prev_end:
                        continue

                    if gap.duration_min >= req.estimated_duration_min:
                        slot_start = gap.start_dt
                        slot_end = slot_start + timedelta(minutes=req.estimated_duration_min)

                        # Check deadline
                        if req.required_by and slot_end > req.required_by:
                            continue

                        # Gap is viable!
                        new_primary = Block(
                            block_request_id=req.id,
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
                            block_request_id=req.id,
                            block_section_id=sec.id,
                            previous_start=prev_start,
                            previous_end=prev_end,
                            new_start=new_primary.planned_start,
                            new_end=new_primary.planned_end,
                            reason="reoptimized_due_to_delay",
                        )
                        db.add(gap_hist)

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
                                f"Defect {defect_code} successfully rescheduled into next free gap on {sec.section_code} "
                                f"({new_primary.planned_start.strftime('%Y-%m-%d %H:%M')} - "
                                f"{new_primary.planned_end.strftime('%H:%M')})."
                            ),
                            defect_code=defect_code,
                            section_code=sec.section_code,
                            action_taken="GAP_RESCHEDULED",
                        )
                        generated_notifications.append(DepartmentNotificationSchema(**notif_green))
                        break

            # --- Case C: Defer to Pending ---
            if not rescheduled:
                req.status = "pending"
                if defect:
                    defect.status = "open"

                notif_amber = add_notification(
                    department=dept,
                    notif_type="AMBER",
                    title=f"RESCHEDULING DEFERRED: {defect_code}",
                    message=(
                        f"No viable shadow or free gap found on {sec.section_code} before deadline "
                        f"{req.required_by}. Request deferred to pending for controller review."
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
                        train_number=train.train_number,
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
                            f"Block revoked due to Train {train.train_number} delay. "
                            f"No slot before deadline {req.required_by}. Deferred to pending."
                        ),
                    )
                )
            else:
                details.append(
                    ConflictResolutionDetailSchema(
                        conflict_type="train_vs_block",
                        section_code=sec.section_code,
                        train_number=train.train_number,
                        train_forecast_entry=sched.forecast_entry,
                        train_forecast_exit=sched.forecast_exit,
                        block_id=block.id,
                        block_planned_start=prev_start,
                        block_planned_end=prev_end,
                        defect_code=defect_code,
                        defect_department=dept,
                        criticality_score=crit_score,
                        severity=severity,
                        decision="block_revoked_and_rescheduled",
                        rescheduled_slot=rescheduled_info,
                        notes=(
                            f"Block revoked due to Train {train.train_number} delay. "
                            f"Successfully rescheduled as {rescheduled_info['type'].upper()} block."
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
    criticality_threshold: int = 70,
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
