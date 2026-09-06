"""
Google OR-Tools CP-SAT formulation for corridor block allocation.
Maximizes total scheduled criticality score while enforcing:
1. No-overlap between maintenance blocks on the same section.
2. Placement exclusively within computed free gaps (respecting train safety buffers).
3. Completion prior to request deadline (required_by).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
from uuid import UUID
from ortools.sat.python import cp_model
from backend.optimizer.gap_calculator import FreeGap

logger = logging.getLogger("backend.optimizer.cpsat")

@dataclass
class PendingRequestDTO:
    id: UUID
    source_system: str
    block_section_id: UUID
    section_code: str
    criticality_score: int
    estimated_duration_min: int
    required_by: Optional[datetime]
    defect_code: Optional[str] = None
    defect_type: Optional[str] = None

@dataclass
class ScheduledAllocation:
    block_request_id: UUID
    block_section_id: UUID
    section_code: str
    planned_start: datetime
    planned_end: datetime
    duration_min: int
    criticality_score: int
    source_system: str
    defect_code: Optional[str] = None
    defect_type: Optional[str] = None

@dataclass
class SolverResult:
    status: str
    scheduled_allocations: List[ScheduledAllocation]
    unscheduled_request_ids: List[UUID]
    total_criticality: int
    solver_wall_time_sec: float

def solve_block_allocations(
    requests: List[PendingRequestDTO],
    section_gaps: Dict[UUID, List[FreeGap]],
    horizon_start: datetime,
    horizon_end: datetime,
    max_solve_time_sec: int = 30,
) -> SolverResult:
    """
    Executes CP-SAT optimization to schedule pending block requests into corridor gaps.
    """
    if horizon_start.tzinfo is None:
        horizon_start = horizon_start.replace(tzinfo=timezone.utc)
    if horizon_end.tzinfo is None:
        horizon_end = horizon_end.replace(tzinfo=timezone.utc)

    total_horizon_minutes = int((horizon_end - horizon_start).total_seconds() // 60)
    if total_horizon_minutes <= 0 or not requests:
        return SolverResult(
            status="EMPTY",
            scheduled_allocations=[],
            unscheduled_request_ids=[r.id for r in requests],
            total_criticality=0,
            solver_wall_time_sec=0.0,
        )

    model = cp_model.CpModel()

    # Track variables per request
    is_scheduled_vars: Dict[UUID, cp_model.IntVar] = {}
    start_vars: Dict[UUID, cp_model.IntVar] = {}
    end_vars: Dict[UUID, cp_model.IntVar] = {}
    interval_vars: Dict[UUID, cp_model.IntervalVar] = {}
    section_intervals: Dict[UUID, List[cp_model.IntervalVar]] = {}
    definitely_unschedulable: List[UUID] = []

    for req in requests:
        duration = req.estimated_duration_min
        sec_id = req.block_section_id
        gaps = section_gaps.get(sec_id, [])

        # 1. Determine deadline bound in minutes
        if req.required_by:
            req_by = req.required_by
            if req_by.tzinfo is None:
                req_by = req_by.replace(tzinfo=timezone.utc)
            deadline_m = int((req_by - horizon_start).total_seconds() // 60)
            max_end = min(total_horizon_minutes, max(0, deadline_m))
        else:
            max_end = total_horizon_minutes

        # 2. Filter eligible gaps
        eligible_gaps = [
            g for g in gaps
            if g.duration_min >= duration and (g.start_min + duration) <= max_end
        ]

        if not eligible_gaps:
            definitely_unschedulable.append(req.id)
            continue

        # 3. Create CP-SAT decision variables for request
        req_id_str = str(req.id)[:8]
        is_sched = model.NewBoolVar(f"is_sched_{req_id_str}")
        start_v = model.NewIntVar(0, total_horizon_minutes - duration, f"start_{req_id_str}")
        end_v = model.NewIntVar(duration, total_horizon_minutes, f"end_{req_id_str}")
        model.Add(end_v == start_v + duration)

        # Optional interval variable for no-overlap constraint
        interval_v = model.NewOptionalIntervalVar(
            start_v, duration, end_v, is_sched, f"interval_{req_id_str}"
        )

        is_scheduled_vars[req.id] = is_sched
        start_vars[req.id] = start_v
        end_vars[req.id] = end_v
        interval_vars[req.id] = interval_v

        if sec_id not in section_intervals:
            section_intervals[sec_id] = []
        section_intervals[sec_id].append(interval_v)

        # 4. Gap choice boolean variables
        gap_choice_vars: List[cp_model.IntVar] = []
        for g in eligible_gaps:
            g_choice = model.NewBoolVar(f"g_{req_id_str}_{g.gap_id}")
            gap_choice_vars.append(g_choice)

            # When gap is chosen, start and end must fit strictly inside
            gap_effective_end = min(g.end_min, max_end)
            model.Add(start_v >= g.start_min).OnlyEnforceIf(g_choice)
            model.Add(end_v <= gap_effective_end).OnlyEnforceIf(g_choice)

        # If scheduled, exactly one eligible gap must be chosen; if not scheduled, zero
        model.Add(sum(gap_choice_vars) == is_sched)

    # 5. Add NoOverlap constraint per section
    for sec_id, intervals in section_intervals.items():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)

    # 6. Objective: Maximize total criticality score with early-start preference
    objective_terms = []
    for req in requests:
        if req.id in is_scheduled_vars:
            is_sched = is_scheduled_vars[req.id]
            start_v = start_vars[req.id]
            # Primary weight on criticality, slight tie-breaker penalty for late starts
            score_weight = int(req.criticality_score * 1000)
            objective_terms.append(score_weight * is_sched - start_v)

    if objective_terms:
        model.Maximize(sum(objective_terms))

    # 7. Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_solve_time_sec)
    solver.parameters.num_search_workers = 4

    status_code = solver.Solve(model)
    status_str = solver.StatusName(status_code)

    scheduled_allocations: List[ScheduledAllocation] = []
    unscheduled_ids: List[UUID] = list(definitely_unschedulable)
    total_criticality = 0

    req_map = {r.id: r for r in requests}

    for req_id, is_sched in is_scheduled_vars.items():
        req = req_map[req_id]
        if solver.BooleanValue(is_sched):
            st_min = solver.Value(start_vars[req_id])
            start_dt = horizon_start + timedelta(minutes=st_min)
            end_dt = start_dt + timedelta(minutes=req.estimated_duration_min)
            total_criticality += req.criticality_score

            scheduled_allocations.append(ScheduledAllocation(
                block_request_id=req.id,
                block_section_id=req.block_section_id,
                section_code=req.section_code,
                planned_start=start_dt,
                planned_end=end_dt,
                duration_min=req.estimated_duration_min,
                criticality_score=req.criticality_score,
                source_system=req.source_system,
                defect_code=req.defect_code,
                defect_type=req.defect_type,
            ))
        else:
            unscheduled_ids.append(req.id)

    # Sort allocations chronologically
    scheduled_allocations.sort(key=lambda a: a.planned_start)

    return SolverResult(
        status=status_str,
        scheduled_allocations=scheduled_allocations,
        unscheduled_request_ids=unscheduled_ids,
        total_criticality=total_criticality,
        solver_wall_time_sec=solver.WallTime(),
    )
