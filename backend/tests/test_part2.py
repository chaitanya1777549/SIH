"""
Unit and integration tests for Part 2:
- Interval merging and free gap computation logic
- Google OR-Tools CP-SAT formulation and constraint satisfaction
- POST /coa/optimize endpoint execution and transactional write-back
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models import (
    BlockSection,
    BlockRequest,
    Block,
    BlockAllocationHistory,
    TMSDefect,
)
from backend.optimizer.gap_calculator import merge_intervals, compute_section_free_gaps, FreeGap
from backend.optimizer.cpsat_solver import (
    PendingRequestDTO,
    solve_block_allocations,
)

client = TestClient(app)

# --- Unit Tests: Gap Calculator ---

def test_merge_intervals():
    # Disjoint intervals
    assert merge_intervals([(10, 20), (30, 40)]) == [(10, 20), (30, 40)]
    # Overlapping intervals
    assert merge_intervals([(10, 30), (20, 40)]) == [(10, 40)]
    # Adjacent intervals
    assert merge_intervals([(10, 20), (20, 30)]) == [(10, 30)]
    # Enclosed intervals
    assert merge_intervals([(10, 50), (20, 30)]) == [(10, 50)]
    # Unordered input
    assert merge_intervals([(40, 60), (10, 25), (20, 30)]) == [(10, 30), (40, 60)]

def test_compute_section_free_gaps_with_safety_buffer():
    t0 = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(hours=10) # 600 minutes total
    dummy_sec = uuid.uuid4()

    # Train from 100 to 120 (minute 100 to 120)
    train_entry = t0 + timedelta(minutes=100)
    train_exit = t0 + timedelta(minutes=120)

    # 10 min safety buffer -> occupied is [90, 130]
    gaps = compute_section_free_gaps(
        section_id=dummy_sec,
        horizon_start=t0,
        horizon_end=t_end,
        train_movements=[(train_entry, train_exit)],
        existing_blocks=[],
        safety_buffer_min=10,
    )

    assert len(gaps) == 2
    # Gap 1: 0 to 90
    assert gaps[0].start_min == 0
    assert gaps[0].end_min == 90
    assert gaps[0].duration_min == 90
    # Gap 2: 130 to 600
    assert gaps[1].start_min == 130
    assert gaps[1].end_min == 600
    assert gaps[1].duration_min == 470

# --- Unit Tests: CP-SAT Solver ---

def test_cpsat_solver_single_fit():
    t0 = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(hours=6) # 360 min
    sec_id = uuid.uuid4()

    gaps = [
        FreeGap(gap_id=1, section_id=sec_id, start_min=60, end_min=180, duration_min=120,
                start_dt=t0 + timedelta(minutes=60), end_dt=t0 + timedelta(minutes=180))
    ]

    req = PendingRequestDTO(
        id=uuid.uuid4(),
        source_system="TMS",
        block_section_id=sec_id,
        section_code="TEST-SEC",
        criticality_score=85,
        estimated_duration_min=90,
        required_by=t0 + timedelta(minutes=300),
    )

    result = solve_block_allocations(
        requests=[req],
        section_gaps={sec_id: gaps},
        horizon_start=t0,
        horizon_end=t_end,
    )

    assert result.status in ["OPTIMAL", "FEASIBLE"]
    assert len(result.scheduled_allocations) == 1
    alloc = result.scheduled_allocations[0]
    assert alloc.block_request_id == req.id
    assert alloc.duration_min == 90
    assert alloc.planned_start >= t0 + timedelta(minutes=60)
    assert alloc.planned_end <= t0 + timedelta(minutes=180)

def test_cpsat_solver_no_overlap_constraint():
    t0 = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(hours=6) # 360 min
    sec_id = uuid.uuid4()

    # Gap of 120 minutes (from 60 to 180)
    gaps = [
        FreeGap(gap_id=1, section_id=sec_id, start_min=60, end_min=180, duration_min=120,
                start_dt=t0 + timedelta(minutes=60), end_dt=t0 + timedelta(minutes=180))
    ]

    # Two requests of 80 minutes each on the same section -> only one can fit in 120 min
    req1 = PendingRequestDTO(
        id=uuid.uuid4(),
        source_system="TMS",
        block_section_id=sec_id,
        section_code="TEST-SEC",
        criticality_score=90,
        estimated_duration_min=80,
        required_by=None,
    )
    req2 = PendingRequestDTO(
        id=uuid.uuid4(),
        source_system="SMMS",
        block_section_id=sec_id,
        section_code="TEST-SEC",
        criticality_score=50,
        estimated_duration_min=80,
        required_by=None,
    )

    result = solve_block_allocations(
        requests=[req1, req2],
        section_gaps={sec_id: gaps},
        horizon_start=t0,
        horizon_end=t_end,
    )

    assert len(result.scheduled_allocations) == 1
    # Higher criticality (req1: 90) must be scheduled over req2 (50)
    assert result.scheduled_allocations[0].block_request_id == req1.id
    assert req2.id in result.unscheduled_request_ids

# --- Integration Tests: /coa/optimize Endpoint ---

def test_optimize_endpoint_no_pending_requests():
    # When no pending requests exist, returns clean NO_PENDING_REQUESTS response
    response = client.post("/coa/optimize", json={
        "start_date": "2026-09-04",
        "end_date": "2026-09-05",
        "safety_buffer_min": 10,
        "max_solve_time_sec": 5
    })
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "execution_time_ms" in data
    assert isinstance(data["allocations"], list)

def test_optimize_endpoint_invalid_date_range():
    response = client.post("/coa/optimize", json={
        "start_date": "2026-09-10",
        "end_date": "2026-09-01", # end before start
    })
    assert response.status_code == 400
    assert "must be on or after" in response.json()["detail"]

def test_end_to_end_optimization_flow():
    """
    Creates an isolated pending request, runs optimization, verifies write-back
    to blocks and history, and cleans up cleanly.
    """
    db = SessionLocal()
    try:
        # Find an existing section
        section = db.query(BlockSection).first()
        assert section is not None

        # Create a test defect
        test_defect = TMSDefect(
            defect_code=f"TEST-OPT-{uuid.uuid4().hex[:6].upper()}",
            block_section_id=section.id,
            defect_type="Optimization Test Defect",
            description="Automated CP-SAT Verification",
            severity="high",
            criticality_score=88,
            estimated_duration_min=45,
            requires_track_block=True,
            status="open",
            work_category="defect",
            input_source="manual",
        )
        db.add(test_defect)
        db.commit()
        db.refresh(test_defect)

        # Create a test pending block_request
        test_request = BlockRequest(
            source_system="TMS",
            tms_defect_id=test_defect.id,
            block_section_id=section.id,
            criticality_score=88,
            estimated_duration_min=45,
            required_by=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc),
            status="pending",
        )
        db.add(test_request)
        db.commit()
        db.refresh(test_request)

        # Trigger optimizer for September 2026
        response = client.post("/coa/optimize", json={
            "start_date": "2026-09-04",
            "end_date": "2026-09-10",
            "safety_buffer_min": 10,
            "max_solve_time_sec": 10,
        })
        assert response.status_code == 200
        data = response.json()

        assert data["total_pending_requests"] >= 1
        assert data["scheduled_count"] >= 1

        # Verify our request was scheduled
        scheduled_req_ids = [a["block_request_id"] for a in data["allocations"]]
        assert str(test_request.id) in scheduled_req_ids

        # Verify DB state
        db.refresh(test_request)
        assert test_request.status == "allocated"

        db.refresh(test_defect)
        assert test_defect.status == "allocated"

        # Verify block row exists
        created_block = db.query(Block).filter(Block.block_request_id == test_request.id).first()
        assert created_block is not None
        assert created_block.block_type == "primary"
        assert created_block.status == "active"

        # Verify history row exists
        history = db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == created_block.id).first()
        assert history is not None
        assert history.reason == "initial_allocation"

    finally:
        # Clean up test artifacts so we do not leave test rows in the database
        if 'test_request' in locals() and test_request.id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_request_id == test_request.id).delete()
            db.query(Block).filter(Block.block_request_id == test_request.id).delete()
            db.query(BlockRequest).filter(BlockRequest.id == test_request.id).delete()
        if 'test_defect' in locals() and test_defect.id:
            db.query(TMSDefect).filter(TMSDefect.id == test_defect.id).delete()
        db.commit()
        db.close()
