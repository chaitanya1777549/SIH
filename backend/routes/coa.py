"""
COA (Central Operations and Allocation) routes using SQLAlchemy.
Provides corridor monitoring, train movements, block sections, and block schedules.
Optimized with joinedload to eliminate N+1 latency over Supabase connection.
"""
from datetime import date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from backend.database import get_db
from backend.models import Station, BlockSection, TrainSchedule, Block, BlockRequest
from backend.schemas import (
    StationSchema,
    BlockSectionSchema,
    TrainMovementSchema,
    BlockDetailSchema,
    OptimizeRequestSchema,
    OptimizeResponseSchema,
    ShadowCheckRequestSchema,
    ShadowCheckResponseSchema,
    ShadowAttachRequestSchema,
    ShadowAttachResponseSchema,
    ShadowDiscardRequestSchema,
    ShadowDiscardResponseSchema,
    TrainDelayUpdateRequestSchema,
    TrainDelayUpdateResponseSchema,
    ReOptimizeRequestSchema,
    ReOptimizeResponseSchema,
    DelayAndReoptimizeRequestSchema,
    DepartmentNotificationSchema,
)
from backend.optimizer.service import run_corridor_optimization
from backend.shadow.engine import (
    find_shadow_candidates_for_block,
    find_all_corridor_shadow_opportunities,
    attach_shadow_block,
    discard_shadow_proposal,
)
from backend.reoptimizer.engine import (
    propagate_train_delay,
    resolve_conflicts_and_reoptimize,
    delay_and_reoptimize,
    get_all_notifications,
)

router = APIRouter(prefix="/coa", tags=["COA Controller"])

@router.get("/stations", response_model=List[StationSchema])
def get_stations(db: Session = Depends(get_db)):
    """
    Retrieve all corridor stations ordered sequentially from VSKP to BZA via SQLAlchemy.
    """
    stations = db.query(Station).order_by(Station.sequence_on_corridor.asc()).all()
    return stations

@router.get("/sections", response_model=List[BlockSectionSchema])
def get_block_sections(db: Session = Depends(get_db)):
    """
    Retrieve all corridor block sections with station names and track codes via SQLAlchemy.
    Eager-loads related stations and tracks in a single query.
    """
    sections = (
        db.query(BlockSection)
        .options(
            joinedload(BlockSection.from_station),
            joinedload(BlockSection.to_station),
            joinedload(BlockSection.track),
        )
        .order_by(BlockSection.sequence_order.asc())
        .all()
    )
    
    results = []
    for s in sections:
        results.append(BlockSectionSchema(
            id=s.id,
            section_code=s.section_code,
            from_station_id=s.from_station_id,
            from_station_code=s.from_station.station_code if s.from_station else None,
            from_station_name=s.from_station.station_name if s.from_station else None,
            to_station_id=s.to_station_id,
            to_station_code=s.to_station.station_code if s.to_station else None,
            to_station_name=s.to_station.station_name if s.to_station else None,
            track_id=s.track_id,
            track_code=s.track.track_code if s.track else None,
            length_km=float(s.length_km) if s.length_km is not None else None,
            sequence_order=s.sequence_order,
            created_at=s.created_at,
        ))
    return results

@router.get("/trains", response_model=List[TrainMovementSchema])
def get_train_movements(
    date_val: Optional[date] = Query(None, alias="date", description="Filter train movements by service date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Retrieve train movements across corridor sections for a specific service date via SQLAlchemy.
    Eager-loads trains and sections in a single query.
    """
    query_date = date_val or date(2026, 9, 4)
    schedules = (
        db.query(TrainSchedule)
        .options(
            joinedload(TrainSchedule.train),
            joinedload(TrainSchedule.block_section),
        )
        .filter(TrainSchedule.service_date == query_date)
        .order_by(TrainSchedule.forecast_entry.asc(), TrainSchedule.block_section_id.asc())
        .all()
    )
    
    results = []
    for s in schedules:
        results.append(TrainMovementSchema(
            id=s.id,
            train_id=s.train_id,
            train_number=s.train.train_number if s.train else "UNKNOWN",
            train_name=s.train.train_name if s.train else None,
            train_type=s.train.train_type if s.train else None,
            block_section_id=s.block_section_id,
            section_code=s.block_section.section_code if s.block_section else "",
            sequence_order=s.block_section.sequence_order if s.block_section else 0,
            service_date=s.service_date,
            scheduled_entry=s.scheduled_entry,
            scheduled_exit=s.scheduled_exit,
            forecast_entry=s.forecast_entry,
            forecast_exit=s.forecast_exit,
            delay_minutes=s.delay_minutes,
            status=s.status,
        ))
    return results

@router.get("/blocks", response_model=List[BlockDetailSchema])
def get_active_blocks(
    date_val: Optional[date] = Query(None, alias="date", description="Filter blocks active on date (YYYY-MM-DD)"),
    start_date: Optional[date] = Query(None, description="Filter blocks active on or after start_date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter blocks active on or before end_date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status ('active', 'completed', or omit for all)"),
    db: Session = Depends(get_db)
):
    """
    Retrieve all blocks (primary and shadow) active on the corridor via SQLAlchemy.
    Supports single date filtering, date range (start_date to end_date), or full month.
    Eager-loads sections, stations, requests, and linked defects in a single query.
    """
    query = (
        db.query(Block)
        .options(
            joinedload(Block.block_section).joinedload(BlockSection.from_station),
            joinedload(Block.block_section).joinedload(BlockSection.to_station),
            joinedload(Block.block_request).joinedload(BlockRequest.tms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.smms_defect),
            joinedload(Block.block_request).joinedload(BlockRequest.tdms_defect),
        )
    )
    
    if status and status.lower() != "all":
        query = query.filter(Block.status == status.lower())

    if start_date and end_date:
        query = query.filter(
            func.date(Block.planned_start) <= end_date,
            func.date(Block.planned_end) >= start_date,
        )
    elif start_date:
        query = query.filter(func.date(Block.planned_end) >= start_date)
    elif end_date:
        query = query.filter(func.date(Block.planned_start) <= end_date)
    elif date_val:
        query = query.filter(
            func.date(Block.planned_start) <= date_val,
            func.date(Block.planned_end) >= date_val,
        )
        
    blocks = query.order_by(Block.planned_start.asc()).all()
    
    results = []
    for b in blocks:
        sec = b.block_section
        req = b.block_request
        defect = None
        if req:
            defect = req.tms_defect or req.smms_defect or req.tdms_defect
            
        duration_min = round((b.planned_end - b.planned_start).total_seconds() / 60)
        
        results.append(BlockDetailSchema(
            id=b.id,
            block_request_id=b.block_request_id,
            block_section_id=b.block_section_id,
            section_code=sec.section_code if sec else "",
            from_station_code=sec.from_station.station_code if sec and sec.from_station else None,
            to_station_code=sec.to_station.station_code if sec and sec.to_station else None,
            planned_start=b.planned_start,
            planned_end=b.planned_end,
            duration_min=int(duration_min),
            status=b.status,
            block_type=b.block_type,
            parent_block_id=b.parent_block_id,
            source_system=req.source_system if req else None,
            defect_code=defect.defect_code if defect else None,
            defect_type=defect.defect_type if defect else None,
            criticality_score=req.criticality_score if req else None,
            optimization_run_at=b.optimization_run_at,
            created_at=b.created_at,
        ))
    return results

@router.post("/optimize", response_model=OptimizeResponseSchema)
def optimize_corridor_blocks(
    payload: OptimizeRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Triggers the Google OR-Tools CP-SAT automatic block optimizer for all pending
    block requests within the specified date horizon.
    """
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date.")

    return run_corridor_optimization(
        db=db,
        start_date=payload.start_date,
        end_date=payload.end_date,
        safety_buffer_min=payload.safety_buffer_min,
        max_solve_time_sec=payload.max_solve_time_sec,
    )

@router.post("/shadow-check", response_model=ShadowCheckResponseSchema)
def check_block_shadow_candidates_post(
    payload: ShadowCheckRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Evaluates an existing primary block against pending requests and open defects
    on the exact same section to discover viable shadow block candidates (POST with JSON body).
    """
    return find_shadow_candidates_for_block(db=db, block_id=payload.block_id)

@router.get("/shadow-check", response_model=ShadowCheckResponseSchema)
def check_block_shadow_candidates_get(
    block_id: UUID = Query(..., description="UUID of the primary block to check"),
    db: Session = Depends(get_db)
):
    """
    Evaluates an existing primary block against pending requests and open defects
    on the exact same section to discover viable shadow block candidates (GET with query param).
    """
    return find_shadow_candidates_for_block(db=db, block_id=block_id)


@router.get("/shadow-opportunities", response_model=List[ShadowCheckResponseSchema])
def list_corridor_shadow_opportunities(
    db: Session = Depends(get_db)
):
    """
    Scans all active primary blocks across the corridor and returns
    those with one or more viable shadow block opportunities.
    """
    return find_all_corridor_shadow_opportunities(db=db)

@router.post("/shadow-attach", response_model=ShadowAttachResponseSchema)
def controller_attach_shadow_block(
    payload: ShadowAttachRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Controller approval action to attach a shadow block to an existing primary block.
    Inserts child block (block_type='shadow'), writes audit trail in block_allocation_history,
    updates defect status to 'allocated', and triggers green approval notification.
    """
    return attach_shadow_block(db=db, payload=payload)

@router.post("/shadow-discard", response_model=ShadowDiscardResponseSchema)
def controller_discard_shadow_proposal(
    payload: ShadowDiscardRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Controller discards a candidate shadow block proposal,
    producing a red notification back to the originating department interface.
    """
    return discard_shadow_proposal(db=db, payload=payload)


@router.post("/trains/update-delay", response_model=TrainDelayUpdateResponseSchema)
def update_train_delay_at_station(
    payload: TrainDelayUpdateRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Updates train delay at a specific station and propagates downstream
    along the train's journey on the corridor.
    """
    return propagate_train_delay(
        db=db,
        train_number=payload.train_number,
        service_date=payload.service_date,
        station_code=payload.station_code,
        delay_minutes=payload.delay_minutes,
    )

@router.post("/reoptimize", response_model=ReOptimizeResponseSchema)
def reoptimize_corridor_conflicts(
    payload: ReOptimizeRequestSchema,
    db: Session = Depends(get_db)
):
    """
    Scans for conflicts between updated train timetables and active blocks,
    executing the intelligent decision matrix:
    - High Criticality: Train is diverted; maintenance block preserved.
    - Normal/Low Criticality: Maintenance block is revoked and immediately rescheduled
      into a shadow block or the next free gap before deadline.
    """
    return resolve_conflicts_and_reoptimize(
        db=db,
        service_date=payload.service_date,
        section_code=payload.section_code,
        criticality_threshold=payload.criticality_threshold,
    )

@router.post("/trains/delay-and-reoptimize")
def one_click_delay_and_reoptimize(
    payload: DelayAndReoptimizeRequestSchema,
    db: Session = Depends(get_db)
):
    """
    One-click COA controller action:
    Applies station train delay propagation and immediately runs corridor re-optimization.
    """
    return delay_and_reoptimize(
        db=db,
        train_number=payload.train_number,
        service_date=payload.service_date,
        station_code=payload.station_code,
        delay_minutes=payload.delay_minutes,
        criticality_threshold=payload.criticality_threshold,
    )

@router.get("/notifications", response_model=List[DepartmentNotificationSchema])
def get_corridor_notifications(
    department: Optional[str] = Query(None, description="Filter by department (TMS, SMMS, TDMS, COA)"),
    limit: int = Query(50, ge=1, le=200, description="Max notifications to return"),
):
    """
    Streams live operational and department notifications (GREEN approvals, RED revocations, BLUE diversions).
    """
    return get_all_notifications(department=department, limit=limit)




