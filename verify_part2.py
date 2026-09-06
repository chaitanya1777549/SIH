r"""
Standalone Verification Script for Part 2: Google OR-Tools CP-SAT Optimizer Core.
Verifies:
1. OR-Tools installation and CP-SAT solver functionality.
2. Gap calculation and train safety buffer padding.
3. CP-SAT mathematical optimization and constraint satisfaction.
4. Live POST /coa/optimize execution against Supabase PostgreSQL via SQLAlchemy.
5. Transactional write-back to blocks, block_allocation_history, and defect status mirroring.

Run with:
    .\myenv\Scripts\python.exe verify_part2.py
"""
import sys
import uuid
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models import BlockSection, BlockRequest, Block, BlockAllocationHistory, TMSDefect
from backend.optimizer.gap_calculator import merge_intervals, compute_section_free_gaps, FreeGap
from backend.optimizer.cpsat_solver import PendingRequestDTO, solve_block_allocations

def main():
    print("=" * 75)
    print("SIH26027 — Automatic Block Planning Prototype: Part 2 Verification")
    print("=" * 75)

    client = TestClient(app)

    # 1. OR-Tools CP-SAT Environment Check
    print("\n[1/5] Checking Google OR-Tools CP-SAT Environment...")
    try:
        from ortools.sat.python import cp_model
        model = cp_model.CpModel()
        x = model.NewIntVar(0, 10, "x")
        model.Maximize(x)
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        if status == cp_model.OPTIMAL and solver.Value(x) == 10:
            print("  --> SUCCESS: Google OR-Tools CP-SAT solver is operational (Status: OPTIMAL)")
        else:
            print(f"  --> FAILED: Unexpected solver status {status}")
            sys.exit(1)
    except Exception as e:
        print(f"  --> FAILED to load OR-Tools: {e}")
        sys.exit(1)

    # 2. Free Gap Computation & Safety Buffer Check
    print("\n[2/5] Verifying Free Gap Computation & Safety Buffer Logic...")
    t0 = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(hours=10) # 600 mins
    dummy_sec = uuid.uuid4()
    train_entry = t0 + timedelta(minutes=120)
    train_exit = t0 + timedelta(minutes=150)
    buffer_min = 10

    gaps = compute_section_free_gaps(
        section_id=dummy_sec,
        horizon_start=t0,
        horizon_end=t_end,
        train_movements=[(train_entry, train_exit)],
        existing_blocks=[],
        safety_buffer_min=buffer_min,
    )
    # Train is 120-150. Buffer 10 -> Occupied is [110, 160].
    # Expected gaps: [0, 110] (110 min) and [160, 600] (440 min).
    if len(gaps) == 2 and gaps[0].duration_min == 110 and gaps[1].duration_min == 440:
        print(f"  --> SUCCESS: Gap engine correctly applied {buffer_min}-min safety buffer:")
        print(f"      Gap 1: 00:00 to 01:50 (110 mins free before train buffer)")
        print(f"      Gap 2: 02:40 to 10:00 (440 mins free after train buffer)")
    else:
        print(f"  --> FAILED: Gaps output mismatch: {gaps}")
        sys.exit(1)

    # 3. CP-SAT Solver Constraint Satisfaction Check
    print("\n[3/5] Verifying CP-SAT Solver Constraint Enforcement...")
    req1 = PendingRequestDTO(
        id=uuid.uuid4(),
        source_system="TMS",
        block_section_id=dummy_sec,
        section_code="TEST-SEC",
        criticality_score=95,
        estimated_duration_min=90,
        required_by=None,
    )
    req2 = PendingRequestDTO(
        id=uuid.uuid4(),
        source_system="SMMS",
        block_section_id=dummy_sec,
        section_code="TEST-SEC",
        criticality_score=40,
        estimated_duration_min=90,
        required_by=None,
    )
    # In a 110-minute gap, only ONE 90-minute block can fit
    result = solve_block_allocations(
        requests=[req1, req2],
        section_gaps={dummy_sec: [gaps[0]]},
        horizon_start=t0,
        horizon_end=t_end,
    )
    if (len(result.scheduled_allocations) == 1 and
        result.scheduled_allocations[0].block_request_id == req1.id and
        req2.id in result.unscheduled_request_ids):
        print("  --> SUCCESS: Solver satisfied NoOverlap constraint and prioritized higher criticality:")
        print(f"      Scheduled: Request #{str(req1.id)[:8]} (Score: 95, Duration: 90m)")
        print(f"      Unscheduled: Request #{str(req2.id)[:8]} (Score: 40, Due to section capacity)")
    else:
        print(f"  --> FAILED: CP-SAT solver constraint check failed: {result}")
        sys.exit(1)

    # 4. Optimizer API Endpoint Check
    print("\n[4/5] Testing POST /coa/optimize Endpoint via FastAPI...")
    resp = client.post("/coa/optimize", json={
        "start_date": "2026-09-04",
        "end_date": "2026-09-08",
        "safety_buffer_min": 10,
        "max_solve_time_sec": 10,
    })
    if resp.status_code == 200:
        data = resp.json()
        print(f"  --> SUCCESS: /coa/optimize executed in {data['execution_time_ms']} ms")
        print(f"      Status: {data['status']}")
        print(f"      Total Pending Requests: {data['total_pending_requests']}")
        print(f"      Newly Scheduled:        {data['scheduled_count']}")
        print(f"      Remaining Unscheduled:  {data['unscheduled_count']}")
    else:
        print(f"  --> FAILED: {resp.status_code} - {resp.text}")
        sys.exit(1)

    # 5. End-to-End Dynamic Allocation & Write-Back Test
    print("\n[5/5] Testing Dynamic End-to-End Block Allocation & DB Write-Back...")
    db = SessionLocal()
    test_defect = None
    test_request = None
    created_block = None
    try:
        section = db.query(BlockSection).first()
        test_defect = TMSDefect(
            defect_code=f"VERIFY-{uuid.uuid4().hex[:6].upper()}",
            block_section_id=section.id,
            defect_type="Verification Track Irregularity",
            description="End-to-End CP-SAT Optimizer Verification",
            severity="high",
            criticality_score=92,
            estimated_duration_min=60,
            requires_track_block=True,
            status="open",
            work_category="defect",
            input_source="manual",
        )
        db.add(test_defect)
        db.commit()
        db.refresh(test_defect)

        test_request = BlockRequest(
            source_system="TMS",
            tms_defect_id=test_defect.id,
            block_section_id=section.id,
            criticality_score=92,
            estimated_duration_min=60,
            required_by=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc),
            status="pending",
        )
        db.add(test_request)
        db.commit()
        db.refresh(test_request)

        print(f"  --> Created test pending request #{str(test_request.id)[:8]} for defect {test_defect.defect_code}")

        opt_resp = client.post("/coa/optimize", json={
            "start_date": "2026-09-04",
            "end_date": "2026-09-10",
            "safety_buffer_min": 10,
            "max_solve_time_sec": 10,
        })
        if opt_resp.status_code != 200:
            raise RuntimeError(f"Optimizer failed: {opt_resp.text}")

        opt_data = opt_resp.json()
        matching = [a for a in opt_data["allocations"] if a["block_request_id"] == str(test_request.id)]
        if not matching:
            raise RuntimeError("Test request was not allocated by optimizer!")

        alloc = matching[0]
        print(f"  --> OPTIMIZER SCHEDULED BLOCK:")
        print(f"      Section:        {alloc['section_code']}")
        print(f"      Planned Start:  {alloc['planned_start']}")
        print(f"      Planned End:    {alloc['planned_end']} ({alloc['duration_min']} mins)")
        print(f"      Criticality:    {alloc['criticality_score']}")

        # Verify DB records
        db.refresh(test_request)
        db.refresh(test_defect)
        assert test_request.status == "allocated", "Request status not updated to allocated!"
        assert test_defect.status == "allocated", "Defect status not updated to allocated!"

        created_block = db.query(Block).filter(Block.block_request_id == test_request.id).first()
        assert created_block is not None, "Block row was not created in DB!"

        history = db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == created_block.id).first()
        assert history is not None, "History audit record not created in DB!"
        assert history.reason == "initial_allocation"

        print(f"  --> SUCCESS: Verified DB state:")
        print(f"      - blocks row created: id={str(created_block.id)[:8]}, status={created_block.status}")
        print(f"      - block_allocation_history row created: reason={history.reason}")
        print(f"      - block_requests status updated: '{test_request.status}'")
        print(f"      - originating tms_defects status updated: '{test_defect.status}'")

    finally:
        # Clean up test artifacts cleanly
        if test_request and test_request.id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_request_id == test_request.id).delete()
            db.query(Block).filter(Block.block_request_id == test_request.id).delete()
            db.query(BlockRequest).filter(BlockRequest.id == test_request.id).delete()
        if test_defect and test_defect.id:
            db.query(TMSDefect).filter(TMSDefect.id == test_defect.id).delete()
        db.commit()
        db.close()
        print("  --> Cleaned up temporary test rows from database.")

    print("\n" + "=" * 75)
    print("ALL PART 2 OPTIMIZER VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 75)

if __name__ == "__main__":
    main()
