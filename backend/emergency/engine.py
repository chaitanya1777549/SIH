"""
Emergency Mode Engine (Section 6 & Phase D).
Handles:
1. Emergency incident creation & asset identification.
2. Train approach and corridor conflict analysis.
3. Rule-based heuristic action recommendation (Hold / Divert / Block / Notify).
4. Multi-option emergency block evaluation (Emergency blocks are dedicated primary possessions and are NEVER checked for shadow blocks):
   - Safe sustainable time verification (disqualifies delayed gap windows).
   - Option 1: Immediate Emergency Track Closure (+15m, full isolation).
   - Option 2: Single-Line Bi-Directional Working / Divert Traffic.
   - Option 3: Targeted Single-Train Hold or Staggered Resource Possession.
   - Option 4: Earliest Sustainable Natural Gap.
5. Controller confirmation, atomic emergency block creation, audit logging, and safety release flow.
"""
import uuid
import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from backend.models import (
    EmergencyIncident,
    BlockSection,
    TrainSchedule,
    Train,
    Block,
    BlockRequest,
    BlockAllocationHistory,
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
)
from backend.optimizer.gap_calculator import compute_section_free_gaps
from backend.reoptimizer.engine import add_notification, propagate_train_delay

logger = logging.getLogger("backend.emergency")


def get_incident_defect(incident: EmergencyIncident, db: Session) -> Tuple[str, Any]:
    """Returns (department, defect_object) for an emergency incident."""
    if incident.tms_defect_id:
        defect = db.query(TMSDefect).filter(TMSDefect.id == incident.tms_defect_id).first()
        return "TMS", defect
    elif incident.smms_defect_id:
        defect = db.query(SMMSDefect).filter(SMMSDefect.id == incident.smms_defect_id).first()
        return "SMMS", defect
    elif incident.tdms_defect_id:
        defect = db.query(TDMSDefect).filter(TDMSDefect.id == incident.tdms_defect_id).first()
        return "TDMS", defect
    return incident.source_system, None


def create_emergency_incident(
    db: Session,
    source_system: str,
    block_section_id: UUID,
    reported_text: str,
    defect_id: Optional[UUID] = None,
    defect_type: Optional[str] = None,
    severity: Optional[str] = "critical",
    estimated_duration_min: int = 90,
    required_by: Optional[datetime] = None,
) -> EmergencyIncident:
    """
    Ingests an emergency defect report and registers it into emergency_incidents.
    If defect_id is omitted, automatically creates a corresponding department defect record.
    """
    source = source_system.upper()
    if source not in ("TMS", "SMMS", "TDMS"):
        raise HTTPException(status_code=400, detail="source_system must be TMS, SMMS, or TDMS")

    section = db.query(BlockSection).filter(BlockSection.id == block_section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail=f"BlockSection '{block_section_id}' not found")

    tms_id = None
    smms_id = None
    tdms_id = None

    now = datetime.now(timezone.utc)
    required_deadline = required_by or (now + timedelta(hours=4)) # Standard emergency limit

    if defect_id:
        if source == "TMS":
            tms_id = defect_id
        elif source == "SMMS":
            smms_id = defect_id
        elif source == "TDMS":
            tdms_id = defect_id
    else:
        # Create a critical emergency defect record
        code = f"{source}-EMERG-{uuid.uuid4().hex[:6].upper()}"
        d_type = defect_type or ("Rail Fracture" if source == "TMS" else "Signal Point Failure" if source == "SMMS" else "OHE Wire Breakdown")
        
        if source == "TMS":
            defect = TMSDefect(
                defect_code=code,
                block_section_id=section.id,
                defect_type=d_type,
                description=reported_text,
                severity=severity or "critical",
                criticality_score=95,
                required_by=required_deadline,
                estimated_duration_min=estimated_duration_min,
                requires_track_block=True,
                status="open",
                input_source="emergency",
                raw_report_text=reported_text,
            )
            db.add(defect)
            db.flush()
            tms_id = defect.id
        elif source == "SMMS":
            defect = SMMSDefect(
                defect_code=code,
                block_section_id=section.id,
                defect_type=d_type,
                description=reported_text,
                severity=severity or "critical",
                criticality_score=95,
                required_by=required_deadline,
                estimated_duration_min=estimated_duration_min,
                requires_signal_block=True,
                status="open",
                input_source="emergency",
                raw_report_text=reported_text,
            )
            db.add(defect)
            db.flush()
            smms_id = defect.id
        elif source == "TDMS":
            defect = TDMSDefect(
                defect_code=code,
                block_section_id=section.id,
                defect_type=d_type,
                description=reported_text,
                severity=severity or "critical",
                criticality_score=95,
                required_by=required_deadline,
                estimated_duration_min=estimated_duration_min,
                requires_power_block=True,
                status="open",
                input_source="emergency",
                raw_report_text=reported_text,
            )
            db.add(defect)
            db.flush()
            tdms_id = defect.id

    incident = EmergencyIncident(
        source_system=source,
        tms_defect_id=tms_id,
        smms_defect_id=smms_id,
        tdms_defect_id=tdms_id,
        block_section_id=section.id,
        reported_text=reported_text,
        status="action_recommended",
    )
    db.add(incident)
    db.flush()

    # Pre-compute initial recommendation
    rec_action, rec_reason = determine_heuristic_recommendation(db, incident)
    incident.recommended_action = rec_action
    db.commit()

    add_notification(
        department=source,
        notif_type="RED",
        title=f"EMERGENCY INCIDENT REPORTED: {section.section_code}",
        message=f"Urgent {source} incident on {section.section_code}: '{reported_text}'. Recommended action: {rec_action.upper()}.",
        section_code=section.section_code,
        action_taken="EMERGENCY_REPORTED",
    )

    return incident


def determine_heuristic_recommendation(
    db: Session,
    incident: EmergencyIncident,
    reference_time: Optional[datetime] = None,
) -> Tuple[str, str]:
    """
    Evaluates approaching trains and active blocks to recommend Hold / Divert / Block / Notify.
    """
    now = reference_time or datetime.now(timezone.utc)
    section = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()
    dept, defect = get_incident_defect(incident, db)

    # Check approaching trains within 60 minutes
    upcoming_limit = now + timedelta(minutes=60)
    approaching_trains = (
        db.query(TrainSchedule)
        .options(joinedload(TrainSchedule.train))
        .filter(
            TrainSchedule.block_section_id == incident.block_section_id,
            TrainSchedule.forecast_entry >= now - timedelta(minutes=10),
            TrainSchedule.forecast_entry <= upcoming_limit,
            TrainSchedule.status.in_(["scheduled", "running"]),
        )
        .order_by(TrainSchedule.forecast_entry.asc())
        .all()
    )

    requires_isolation = True
    if defect:
        requires_isolation = getattr(defect, "requires_track_block", getattr(defect, "requires_signal_block", getattr(defect, "requires_power_block", True)))

    if not requires_isolation:
        return "notify", "Defect is off-track/routine; caution order or speed restriction recommended without line possession."

    # Immediate train collision risk (train arriving in <= 15 minutes)
    imminent_trains = [t for t in approaching_trains if (t.forecast_entry - now).total_seconds() <= 900]
    if imminent_trains:
        t_num = imminent_trains[0].train.train_number
        mins = int((imminent_trains[0].forecast_entry - now).total_seconds() // 60)
        return "hold", f"Train {t_num} approaching damaged section in {max(0, mins)}m. Immediate upstream station HOLD recommended to avert derailment risk."

    # If trains are between 15-60m away, evaluate block options
    if len(approaching_trains) > 2:
        return "divert", f"Heavy corridor traffic ({len(approaching_trains)} trains in next hour). DIVERT to loop/alternate route recommended while preparing block."

    return "block", "Track possession (BLOCK) recommended. Safe window can be secured via targeted train hold or immediate track possession."


def generate_emergency_block_options(
    db: Session,
    incident: EmergencyIncident,
    required_duration_min: int = 90,
    reference_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Computes realistic, concrete candidate emergency block options:
    (Rule: Emergency blocks are dedicated safety possessions and are NEVER checked for shadow blocks)
    - Option 1: Immediate Emergency Closure (+15m, full isolation, hold approaching trains at loops).
    - Option 2: Single-Line Bi-Directional Working / Divert Traffic (30 km/h pilot caution).
    - Option 3: Tactical Staggered Hold / Mobilization Runway (only 1 train regulated or crew dispatch).
    - Option 4: Earliest Sustainable Natural Gap (if fitting before maximum safe emergency deadline).
    """
    now = reference_time or datetime.now(timezone.utc)
    dept, defect = get_incident_defect(incident, db)
    sec = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()

    # Determine maximum safe sustainable time for this emergency defect
    max_safe_time = getattr(defect, "required_by", None) if defect else None
    if not max_safe_time:
        max_safe_time = now + timedelta(hours=4) # Default 4h emergency sustainable limit
    if max_safe_time.tzinfo is None:
        max_safe_time = max_safe_time.replace(tzinfo=timezone.utc)

    options: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # Option 1: Immediate Emergency Closure (+15m)
    # -------------------------------------------------------------
    opt1_start = now + timedelta(minutes=15)
    opt1_end = opt1_start + timedelta(minutes=required_duration_min)

    # Calculate conflicting trains in this window (+10m buffer)
    train_overlaps = (
        db.query(TrainSchedule)
        .options(joinedload(TrainSchedule.train))
        .filter(
            TrainSchedule.block_section_id == sec.id,
            TrainSchedule.forecast_entry <= opt1_end + timedelta(minutes=10),
            TrainSchedule.forecast_exit >= opt1_start - timedelta(minutes=10),
            TrainSchedule.status.in_(["scheduled", "running"]),
        )
        .all()
    )

    opt1_trains_count = len(train_overlaps)
    opt1_total_delay = sum(
        max(15, int((opt1_end - t.forecast_entry).total_seconds() // 60))
        for t in train_overlaps
    )
    affected_numbers = [t.train.train_number for t in train_overlaps]

    # Option 1: Emergency Track Block (Hold Approaching Trains at Loops)
    options.append({
        "option_id": "opt-immediate",
        "label": "Option 1: Emergency Track Block (Hold Approaching Trains at Loops)",
        "planned_start": opt1_start.isoformat(),
        "planned_end": opt1_end.isoformat(),
        "duration_min": required_duration_min,
        "trains_affected_count": opt1_trains_count,
        "affected_train_numbers": affected_numbers,
        "total_delay_minutes": opt1_total_delay,
        "is_shadow": False,
        "resource_impact": "Full emergency possession & power/signal isolation. Holds conflicting trains at upstream loops.",
        "sustainable": True,
        "description": f"Immediate line possession ({opt1_start.strftime('%H:%M')} - {opt1_end.strftime('%H:%M')}). Stables {opt1_trains_count} train(s) #{', #'.join(affected_numbers) if affected_numbers else 'none'} in loops (total delay: {opt1_total_delay}m).",
    })

    # Option 2: Single-Line Bi-Directional Working / Divert Traffic via Alternate Line
    divert_delay = max(15, len(train_overlaps) * 20) if train_overlaps else 0
    desc_opt2 = (
        f"Diverts #{', #'.join(affected_numbers)} via opposite line under pilot caution order (30 km/h). Reduces delay to {divert_delay}m without dead-stabling trains."
        if train_overlaps
        else "Implement single-line pilot working on adjacent track to safeguard against incidental traffic during possession."
    )
    options.append({
        "option_id": "opt-divert-single-line",
        "label": "Option 2: Single-Line Working / Divert Traffic (30 km/h Pilot Caution)",
        "planned_start": opt1_start.isoformat(),
        "planned_end": opt1_end.isoformat(),
        "duration_min": required_duration_min,
        "trains_affected_count": len(train_overlaps),
        "affected_train_numbers": affected_numbers,
        "total_delay_minutes": divert_delay,
        "is_shadow": False,
        "resource_impact": "Bi-directional pilot working on adjacent track. Keeps traffic moving with caution speed.",
        "sustainable": True,
        "description": desc_opt2,
    })

    # Option 3: Targeted Single-Train Hold or Staggered Resource Possession
    if train_overlaps:
        first_train = min(train_overlaps, key=lambda t: t.forecast_entry)
        t_num = first_train.train.train_number
        opt2_start = now + timedelta(minutes=25)
        opt2_end = opt2_start + timedelta(minutes=required_duration_min)
        single_delay = int((opt2_end - first_train.forecast_entry).total_seconds() // 60)
        is_opt3_sustainable = opt2_start <= max_safe_time
        options.append({
            "option_id": "opt-single-train-hold",
            "label": f"Option 3: Tactical Staggered Hold (Only Train {t_num} Regulated)",
            "planned_start": opt2_start.isoformat(),
            "planned_end": opt2_end.isoformat(),
            "duration_min": required_duration_min,
            "trains_affected_count": 1,
            "affected_train_numbers": [t_num],
            "total_delay_minutes": max(15, single_delay),
            "is_shadow": False,
            "resource_impact": "Dedicated repair gang; regulates only Train " + t_num + " at upstream loop line.",
            "sustainable": is_opt3_sustainable,
            "description": f"Targeted intervention: Regulate Train {t_num} by {max(15, single_delay)}m to secure uninterrupted {required_duration_min}m window from {opt2_start.strftime('%H:%M')} to {opt2_end.strftime('%H:%M')}." + ("" if is_opt3_sustainable else f" [Caution: Exceeds emergency deadline of {max_safe_time.strftime('%H:%M')}]."),
        })
    else:
        opt3_start = now + timedelta(minutes=30)
        opt3_end = opt3_start + timedelta(minutes=required_duration_min)
        is_opt3_sustainable = opt3_start <= max_safe_time
        options.append({
            "option_id": "opt-staggered-window",
            "label": "Option 3: Staggered Resource Possession (+30m Mobilization)",
            "planned_start": opt3_start.isoformat(),
            "planned_end": opt3_end.isoformat(),
            "duration_min": required_duration_min,
            "trains_affected_count": 0,
            "affected_train_numbers": [],
            "total_delay_minutes": 0,
            "is_shadow": False,
            "resource_impact": "Provides 30-min mobilization runway for tower wagon and maintenance gang dispatch.",
            "sustainable": is_opt3_sustainable,
            "description": f"Staggered start ({opt3_start.strftime('%H:%M')} - {opt3_end.strftime('%H:%M')}). Allows crew equipment staging with zero train delay." + ("" if is_opt3_sustainable else f" [Caution: Exceeds emergency deadline of {max_safe_time.strftime('%H:%M')}]."),
        })

    # -------------------------------------------------------------
    # Option 4: Earliest Natural Gap (Strict Sustainable Check)
    # -------------------------------------------------------------
    # Compute free gaps on this section for today
    horizon_start = now
    horizon_end = now + timedelta(hours=12)

    scheds = (
        db.query(TrainSchedule)
        .filter(
            TrainSchedule.block_section_id == sec.id,
            TrainSchedule.service_date >= now.date(),
            TrainSchedule.service_date <= (now + timedelta(days=1)).date(),
            TrainSchedule.status.in_(["scheduled", "running"]),
        )
        .all()
    )
    train_moves = [(t.forecast_entry, t.forecast_exit) for t in scheds]

    blocks = (
        db.query(Block)
        .filter(
            Block.block_section_id == sec.id,
            Block.status == "active",
        )
        .all()
    )
    block_moves = [(b.planned_start, b.planned_end) for b in blocks]

    free_gaps = compute_section_free_gaps(
        section_id=sec.id,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        train_movements=train_moves,
        existing_blocks=block_moves,
        safety_buffer_min=10,
    )

    for gap in free_gaps:
        # Gap must fit duration and must start before max_safe_time
        if gap.duration_min >= required_duration_min and gap.start_dt <= max_safe_time and gap.start_dt >= (now + timedelta(minutes=20)):
            gap_end = gap.start_dt + timedelta(minutes=required_duration_min)
            options.append({
                "option_id": "opt-natural-gap",
                "label": "Option 4: Earliest Sustainable Natural Gap",
                "planned_start": gap.start_dt.isoformat(),
                "planned_end": gap_end.isoformat(),
                "duration_min": required_duration_min,
                "trains_affected_count": 0,
                "affected_train_numbers": [],
                "total_delay_minutes": 0,
                "is_shadow": False,
                "resource_impact": "Clean scheduled slot; zero train delays or route diversions.",
                "sustainable": True,
                "description": f"Natural corridor free gap from {gap.start_dt.strftime('%H:%M')} to {gap_end.strftime('%H:%M')}. Defect sustained safely within deadline.",
            })
            break

    return options


def confirm_emergency_decision(
    db: Session,
    incident_id: UUID,
    decision: str,
    selected_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Controller confirms an operational decision:
    - If 'block', allocates the chosen option as an emergency Block.
    - Updates incident status to 'confirmed', logs history, and emits department notifications.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"EmergencyIncident '{incident_id}' not found")

    decision_lower = decision.lower()
    if decision_lower not in ("hold", "divert", "block", "notify"):
        raise HTTPException(status_code=400, detail="Decision must be hold, divert, block, or notify")

    now = reference_time or datetime.now(timezone.utc)
    dept, defect = get_incident_defect(incident, db)
    sec = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()

    created_block_id = None
    created_request_id = None

    if decision_lower == "block":
        # Generate options to match the selected option ID
        options = generate_emergency_block_options(db, incident, reference_time=now)
        chosen_opt = None
        if selected_option_id:
            chosen_opt = next((o for o in options if o["option_id"] == selected_option_id), None)
        if not chosen_opt and options:
            chosen_opt = options[0] # Default to Option 1 if unspecified

        if not chosen_opt:
            raise HTTPException(status_code=400, detail="No viable emergency block options available on this section")

        planned_start = datetime.fromisoformat(chosen_opt["planned_start"])
        planned_end = datetime.fromisoformat(chosen_opt["planned_end"])

        # 1. Create BlockRequest with is_emergency=True
        req = BlockRequest(
            source_system=dept,
            tms_defect_id=incident.tms_defect_id,
            smms_defect_id=incident.smms_defect_id,
            tdms_defect_id=incident.tdms_defect_id,
            block_section_id=sec.id,
            criticality_score=getattr(defect, "criticality_score", 95),
            required_by=getattr(defect, "required_by", now + timedelta(hours=4)),
            estimated_duration_min=chosen_opt["duration_min"],
            status="allocated",
            is_emergency=True,
        )
        db.add(req)
        db.flush()
        created_request_id = req.id

        # 2. Create Block (Emergency blocks are dedicated primary possessions, never shadow blocks)
        block = Block(
            block_request_id=req.id,
            block_section_id=sec.id,
            planned_start=planned_start,
            planned_end=planned_end,
            status="active",
            block_type="primary",
            parent_block_id=None,
        )
        db.add(block)
        db.flush()
        created_block_id = block.id

        # 3. Log History
        hist = BlockAllocationHistory(
            block_id=block.id,
            block_request_id=req.id,
            block_section_id=sec.id,
            previous_start=None,
            previous_end=None,
            new_start=planned_start,
            new_end=planned_end,
            reason="emergency_block_allocated",
        )
        db.add(hist)

        # 4. Update Defect status
        if defect:
            defect.status = "allocated"

        incident.block_request_id = req.id

        # Regulate approaching trains at station loop lines and shift schedules past block release
        affected_train_numbers = list(chosen_opt.get("affected_train_numbers", []))
        service_dt = planned_start.date()

        # Also find any trains that directly conflict with this block window on this section
        active_overlaps = (
            db.query(TrainSchedule)
            .join(Train)
            .filter(
                TrainSchedule.block_section_id == sec.id,
                TrainSchedule.service_date == service_dt,
                TrainSchedule.forecast_entry <= planned_end + timedelta(minutes=5),
                TrainSchedule.forecast_exit >= planned_start - timedelta(minutes=5),
            )
            .all()
        )
        for overlap in active_overlaps:
            if overlap.train and overlap.train.train_number not in affected_train_numbers:
                affected_train_numbers.append(overlap.train.train_number)

        stn_code = sec.from_station.station_code if sec.from_station else None

        for target_train_no in affected_train_numbers:
            sched_to_update = (
                db.query(TrainSchedule)
                .join(Train)
                .filter(
                    Train.train_number == target_train_no,
                    TrainSchedule.block_section_id == sec.id,
                    TrainSchedule.service_date == service_dt,
                )
                .first()
            )
            if sched_to_update:
                required_entry = planned_end + timedelta(minutes=5)
                delay_needed = max(15, int((required_entry - sched_to_update.scheduled_entry).total_seconds() // 60))
                propagated = False
                if stn_code:
                    try:
                        propagate_train_delay(
                            db=db,
                            train_number=target_train_no,
                            service_date=service_dt,
                            station_code=stn_code,
                            delay_minutes=delay_needed,
                        )
                        propagated = True
                    except Exception as e:
                        logger.warning(f"Downstream propagation failed for {target_train_no} at {stn_code}: {e}")

                if not propagated:
                    sched_to_update.delay_minutes = max(sched_to_update.delay_minutes, delay_needed)
                    sched_to_update.forecast_entry = required_entry
                    run_duration = sched_to_update.scheduled_exit - sched_to_update.scheduled_entry
                    sched_to_update.forecast_exit = required_entry + run_duration

        add_notification(
            department=dept,
            notif_type="GREEN",
            title=f"EMERGENCY BLOCK CONFIRMED: {sec.section_code}",
            message=f"Controller approved emergency block ({planned_start.strftime('%H:%M')} - {planned_end.strftime('%H:%M')}) for {dept}. Crew authorized for immediate mobilization.",
            section_code=sec.section_code,
            action_taken="EMERGENCY_BLOCK_ALLOCATED",
        )

    else:
        # Hold / Divert / Notify decisions
        notif_type = "BLUE" if decision_lower in ("hold", "divert") else "AMBER"
        add_notification(
            department=dept,
            notif_type=notif_type,
            title=f"EMERGENCY DECISION CONFIRMED: {decision.upper()}",
            message=f"Controller enacted '{decision.upper()}' on {sec.section_code}: {notes or 'Operational safety measures initiated.'}",
            section_code=sec.section_code,
            action_taken=f"EMERGENCY_{decision.upper()}",
        )

    incident.status = "confirmed"
    incident.controller_decision = decision_lower
    incident.confirmed_at = now

    # Also mark any other duplicate unconfirmed incidents on this section as superseded/confirmed
    db.query(EmergencyIncident).filter(
        EmergencyIncident.block_section_id == incident.block_section_id,
        EmergencyIncident.id != incident.id,
        EmergencyIncident.status.in_(["reported", "action_recommended", "escalated_emergency"])
    ).update({"status": "confirmed", "controller_decision": decision_lower}, synchronize_session=False)

    db.commit()

    return {
        "status": "success",
        "incident_id": str(incident.id),
        "decision": decision_lower,
        "confirmed_at": incident.confirmed_at.isoformat(),
        "block_id": str(created_block_id) if created_block_id else None,
        "block_request_id": str(created_request_id) if created_request_id else None,
        "message": f"Emergency decision '{decision.upper()}' confirmed and applied successfully.",
    }


def advance_incident_lifecycle(
    db: Session,
    incident_id: UUID,
    target_status: str,
    officer_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Advances the emergency incident lifecycle:
    - 'repairing': Field team mobilized and active.
    - 'safety_confirmed': Field engineer certifies safety clearance.
    - 'released': Emergency block is released, marked 'completed', and corridor reopened.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"EmergencyIncident '{incident_id}' not found")

    target = target_status.lower()
    valid_transitions = {
        "confirmed": ["repairing", "notified"],
        "notified": ["repairing"],
        "repairing": ["safety_confirmed"],
        "safety_confirmed": ["released"],
    }

    current = incident.status
    if target not in valid_transitions.get(current, []) and target not in ("repairing", "safety_confirmed", "released"):
        raise HTTPException(status_code=400, detail=f"Cannot transition incident from '{current}' to '{target}'")

    dept, defect = get_incident_defect(incident, db)
    sec = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()

    if target == "safety_confirmed":
        add_notification(
            department="COA",
            notif_type="AMBER",
            title=f"SAFETY CONFIRMATION RECEIVED: {sec.section_code}",
            message=f"Field engineers completed repairs on {sec.section_code}. Track certified safe for traffic restoration. Awaiting controller release.",
            section_code=sec.section_code,
            action_taken="SAFETY_CONFIRMED",
        )

    elif target == "released":
        # Release the emergency block if one was allocated
        if incident.block_request_id:
            block = db.query(Block).filter(Block.block_request_id == incident.block_request_id, Block.status == "active").first()
            if block:
                block.status = "completed"
        if defect:
            defect.status = "resolved"

        add_notification(
            department="COA",
            notif_type="GREEN",
            title=f"EMERGENCY BLOCK RELEASED: {sec.section_code}",
            message=f"Section {sec.section_code} certified safe and formally RELEASED by Controller. Normal train operations resumed.",
            section_code=sec.section_code,
            action_taken="CORRIDOR_RELEASED",
        )

    incident.status = target
    db.commit()

    return {
        "status": "success",
        "incident_id": str(incident.id),
        "new_status": target,
        "message": f"Incident transitioned to '{target}'.",
    }


def evaluate_crucial_defect_pipeline(
    db: Session,
    source_system: str,
    block_section_id: UUID,
    reason: str,
    estimated_duration_min: int,
    required_by: Optional[datetime] = None,
    defect_id: Optional[UUID] = None,
    defect_type: Optional[str] = None,
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Automated triage pipeline for crucial department defects:
    1. Checks if a natural free gap can accommodate the defect before required_by.
       If YES -> Schedules standard block request in that gap (No emergency escalation).
    2. If NO free timetable gap exists before the deadline:
       AUTOMATICALLY INVOKES EMERGENCY MODE! (Rule: Emergency blocks are NEVER checked for shadow blocks).
       Creates EmergencyIncident and generates multi-option tactical trade-off cards (Hold / Divert / Immediate Block / Natural Gap).
    """
    now = reference_time or datetime.now(timezone.utc)
    if not required_by or (required_by.tzinfo and required_by <= now):
        required_by = now + timedelta(hours=2)
    elif required_by.tzinfo is None:
        required_by = required_by.replace(tzinfo=timezone.utc)

    sec = db.query(BlockSection).filter(BlockSection.id == block_section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail=f"BlockSection '{block_section_id}' not found")

    # -------------------------------------------------------------
    # Cascade Step 1: Check Natural Free Gap before required_by
    # -------------------------------------------------------------
    scheds = (
        db.query(TrainSchedule)
        .filter(
            TrainSchedule.block_section_id == sec.id,
            TrainSchedule.service_date >= now.date(),
            TrainSchedule.service_date <= (now + timedelta(days=1)).date(),
            TrainSchedule.status.in_(["scheduled", "running"]),
        )
        .all()
    )
    train_moves = [(t.forecast_entry, t.forecast_exit) for t in scheds]

    blocks = (
        db.query(Block)
        .filter(
            Block.block_section_id == sec.id,
            Block.status == "active",
        )
        .all()
    )
    block_moves = [(b.planned_start, b.planned_end) for b in blocks]

    free_gaps = compute_section_free_gaps(
        section_id=sec.id,
        horizon_start=now,
        horizon_end=max(now + timedelta(hours=8), required_by + timedelta(hours=2)),
        train_movements=train_moves,
        existing_blocks=block_moves,
        safety_buffer_min=10,
    )

    for gap in free_gaps:
        if (gap.duration_min >= estimated_duration_min and 
            gap.start_dt >= (now + timedelta(minutes=15)) and 
            (gap.start_dt + timedelta(minutes=estimated_duration_min)) <= required_by):
            
            gap_end = gap.start_dt + timedelta(minutes=estimated_duration_min)
            
            add_notification(
                department=source_system,
                notif_type="GREEN",
                title=f"FREE GAP IDENTIFIED: {sec.section_code}",
                message=f"Natural timetable gap found ({gap.start_dt.strftime('%H:%M')} - {gap_end.strftime('%H:%M')}) before deadline ({required_by.strftime('%H:%M')}). Proposed for standard COA review.",
                section_code=sec.section_code,
                action_taken="FREE_GAP_PROPOSED",
            )
            
            return {
                "cascade_step": "free_gap_found",
                "requires_emergency": False,
                "message": f"Natural timetable gap available ({gap.start_dt.strftime('%H:%M')} - {gap_end.strftime('%H:%M')}). Block scheduled without emergency escalation.",
                "proposed_start": gap.start_dt.isoformat(),
                "proposed_end": gap_end.isoformat(),
                "duration_min": estimated_duration_min,
                "deadline": required_by.isoformat(),
                "incident_id": None,
                "options": [],
            }

    # -------------------------------------------------------------
    # Cascade Step 2: No Free Gap before deadline -> AUTOMATICALLY INVOKE EMERGENCY!
    # (RULE: Emergency blocks are NEVER checked for shadow blocks!)
    # -------------------------------------------------------------
    incident = create_emergency_incident(
        db=db,
        source_system=source_system,
        block_section_id=sec.id,
        reported_text=f"CRUCIAL DEFECT: {reason} | Duration: {estimated_duration_min}m | Deadline: {required_by.strftime('%H:%M')}",
        defect_id=defect_id,
        defect_type=defect_type,
        severity="critical",
        estimated_duration_min=estimated_duration_min,
        required_by=required_by,
    )

    options = generate_emergency_block_options(
        db=db,
        incident=incident,
        required_duration_min=estimated_duration_min,
        reference_time=now,
    )

    add_notification(
        department=source_system,
        notif_type="RED",
        title=f"🚨 EMERGENCY INVOKED: {sec.section_code}",
        message=f"No free timetable gap available before {required_by.strftime('%H:%M')}. Emergency mode automatically triggered! Siren alert activated at COA.",
        section_code=sec.section_code,
        action_taken="EMERGENCY_INVOKED",
    )

    return {
        "cascade_step": "emergency_invoked",
        "requires_emergency": True,
        "message": f"CRITICAL EMERGENCY: No free timetable gap available before {required_by.strftime('%H:%M')}. Emergency mode automatically invoked with active siren alert at COA.",
        "incident_id": str(incident.id),
        "section_code": sec.section_code,
        "deadline": required_by.isoformat(),
        "options": options,
    }

