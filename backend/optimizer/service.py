"""
Optimization coordinator service.
Orchestrates data fetching via SQLAlchemy, gap computation, CP-SAT solve,
and transactional write-back to Supabase PostgreSQL.
"""
import logging
import time
import uuid
from datetime import datetime, date, time as dt_time, timezone
from typing import List, Dict, Tuple
from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from backend.models import (
    BlockRequest,
    Block,
    BlockAllocationHistory,
    TrainSchedule,
    BlockSection,
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
)
from backend.optimizer.gap_calculator import compute_section_free_gaps, FreeGap
from backend.optimizer.cpsat_solver import (
    PendingRequestDTO,
    solve_block_allocations,
    SolverResult,
)
from backend.schemas import OptimizeResponseSchema, AllocationResultSchema

logger = logging.getLogger("backend.optimizer.service")

def run_corridor_optimization(
    db: Session,
    start_date: date,
    end_date: date,
    safety_buffer_min: int = 10,
    max_solve_time_sec: int = 30,
) -> OptimizeResponseSchema:
    """
    Runs the full CP-SAT optimization pipeline over the given date horizon.
    """
    t_start = time.time()

    horizon_start = datetime.combine(start_date, dt_time.min).replace(tzinfo=timezone.utc)
    horizon_end = datetime.combine(end_date, dt_time.max).replace(tzinfo=timezone.utc)

    # 1. Fetch pending block requests
    pending_requests = (
        db.query(BlockRequest)
        .options(
            joinedload(BlockRequest.block_section),
            joinedload(BlockRequest.tms_defect),
            joinedload(BlockRequest.smms_defect),
            joinedload(BlockRequest.tdms_defect),
        )
        .filter(BlockRequest.status == "pending")
        .all()
    )

    if not pending_requests:
        logger.info("No pending block requests found to optimize.")
        execution_time_ms = round((time.time() - t_start) * 1000, 2)
        return OptimizeResponseSchema(
            status="NO_PENDING_REQUESTS",
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            total_pending_requests=0,
            scheduled_count=0,
            unscheduled_count=0,
            total_criticality_scheduled=0,
            allocations=[],
            unscheduled_request_ids=[],
            execution_time_ms=execution_time_ms,
        )

    # 2. Collect unique section IDs needed by pending requests
    relevant_section_ids = list({r.block_section_id for r in pending_requests})

    # 3. Fetch train movements for relevant sections in the horizon
    train_schedules = (
        db.query(TrainSchedule)
        .filter(
            TrainSchedule.block_section_id.in_(relevant_section_ids),
            TrainSchedule.forecast_entry <= horizon_end,
            TrainSchedule.forecast_exit >= horizon_start,
        )
        .all()
    )
    trains_by_section: Dict[UUID, List[Tuple[datetime, datetime]]] = {s: [] for s in relevant_section_ids}
    for ts in train_schedules:
        trains_by_section[ts.block_section_id].append((ts.forecast_entry, ts.forecast_exit))

    # 4. Fetch existing active blocks for relevant sections in the horizon
    existing_blocks = (
        db.query(Block)
        .filter(
            Block.block_section_id.in_(relevant_section_ids),
            Block.status == "active",
            Block.planned_start <= horizon_end,
            Block.planned_end >= horizon_start,
        )
        .all()
    )
    blocks_by_section: Dict[UUID, List[Tuple[datetime, datetime]]] = {s: [] for s in relevant_section_ids}
    for blk in existing_blocks:
        blocks_by_section[blk.block_section_id].append((blk.planned_start, blk.planned_end))

    # 5. Compute free gaps per section
    section_gaps: Dict[UUID, List[FreeGap]] = {}
    for sec_id in relevant_section_ids:
        section_gaps[sec_id] = compute_section_free_gaps(
            section_id=sec_id,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            train_movements=trains_by_section.get(sec_id, []),
            existing_blocks=blocks_by_section.get(sec_id, []),
            safety_buffer_min=safety_buffer_min,
        )

    # 6. Prepare DTOs for CP-SAT solver
    request_dtos: List[PendingRequestDTO] = []
    for r in pending_requests:
        defect = r.tms_defect or r.smms_defect or r.tdms_defect
        request_dtos.append(PendingRequestDTO(
            id=r.id,
            source_system=r.source_system,
            block_section_id=r.block_section_id,
            section_code=r.block_section.section_code if r.block_section else "",
            criticality_score=r.criticality_score,
            estimated_duration_min=r.estimated_duration_min,
            required_by=r.required_by,
            defect_code=defect.defect_code if defect else None,
            defect_type=defect.defect_type if defect else None,
        ))

    # 7. Solve with CP-SAT
    solver_result: SolverResult = solve_block_allocations(
        requests=request_dtos,
        section_gaps=section_gaps,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        max_solve_time_sec=max_solve_time_sec,
    )

    # 8. Transactional write-back for scheduled allocations
    now_utc = datetime.now(timezone.utc)
    allocation_results: List[AllocationResultSchema] = []

    req_entity_map = {r.id: r for r in pending_requests}

    for alloc in solver_result.scheduled_allocations:
        req = req_entity_map[alloc.block_request_id]

        # Insert new primary block
        new_block = Block(
            id=uuid.uuid4(),
            block_request_id=req.id,
            block_section_id=req.block_section_id,
            planned_start=alloc.planned_start,
            planned_end=alloc.planned_end,
            status="active",
            block_type="primary",
            parent_block_id=None,
            optimization_run_at=now_utc,
            created_at=now_utc,
        )
        db.add(new_block)
        db.flush()  # Ensure block exists in DB before history references it

        # Insert audit history record
        history = BlockAllocationHistory(
            id=uuid.uuid4(),
            block_id=new_block.id,
            block_request_id=req.id,
            block_section_id=req.block_section_id,
            previous_start=None,
            previous_end=None,
            new_start=alloc.planned_start,
            new_end=alloc.planned_end,
            reason="initial_allocation",
            changed_at=now_utc,
        )
        db.add(history)

        # Update block_request status
        req.status = "allocated"

        # Mirror status onto originating defect row
        if req.tms_defect_id:
            db.query(TMSDefect).filter(TMSDefect.id == req.tms_defect_id).update({"status": "allocated"})
        elif req.smms_defect_id:
            db.query(SMMSDefect).filter(SMMSDefect.id == req.smms_defect_id).update({"status": "allocated"})
        elif req.tdms_defect_id:
            db.query(TDMSDefect).filter(TDMSDefect.id == req.tdms_defect_id).update({"status": "allocated"})

        allocation_results.append(AllocationResultSchema(
            block_id=new_block.id,
            block_request_id=req.id,
            block_section_id=req.block_section_id,
            section_code=alloc.section_code,
            planned_start=alloc.planned_start,
            planned_end=alloc.planned_end,
            duration_min=alloc.duration_min,
            criticality_score=alloc.criticality_score,
            source_system=alloc.source_system,
            defect_code=alloc.defect_code,
            defect_type=alloc.defect_type,
        ))

    # Commit the transaction atomically
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to commit block allocations: {e}", exc_info=True)
        raise

    execution_time_ms = round((time.time() - t_start) * 1000, 2)

    return OptimizeResponseSchema(
        status=solver_result.status,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        total_pending_requests=len(pending_requests),
        scheduled_count=len(allocation_results),
        unscheduled_count=len(solver_result.unscheduled_request_ids),
        total_criticality_scheduled=solver_result.total_criticality,
        allocations=allocation_results,
        unscheduled_request_ids=solver_result.unscheduled_request_ids,
        execution_time_ms=execution_time_ms,
    )
