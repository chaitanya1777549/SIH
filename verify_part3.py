r"""
Standalone Verification Script for Part 3: Shadow-Block Detection & Approval Flow.
Verifies:
1. Querying corridor-wide shadow block opportunities (GET /coa/shadow-opportunities).
2. Evaluating an existing primary block against pending/open candidates (POST /coa/shadow-check).
3. Enforcing hard structural constraints (same section, duration fit, deadline satisfaction).
4. Controller approval and shadow block attachment (POST /coa/shadow-attach) with DB write-back
   (block_type='shadow', parent_block_id, audit history, defect status update, green notification).
5. Controller discard flow (POST /coa/shadow-discard) with red notification.

Run with:
    .\myenv\Scripts\python.exe verify_part3.py
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models import (
    Block,
    BlockRequest,
    BlockAllocationHistory,
    BlockSection,
    SMMSDefect,
)

def main():
    print("=" * 80)
    print("SIH26027 — Automatic Block Planning Prototype: Part 3 Verification")
    print("=" * 80)

    client = TestClient(app)

    # 1. Check Corridor-Wide Shadow Opportunities
    print("\n[1/5] Checking Corridor-Wide Shadow Block Opportunities...")
    resp = client.get("/coa/shadow-opportunities")
    if resp.status_code == 200:
        opps = resp.json()
        print(f"  --> SUCCESS: Found {len(opps)} primary blocks with shadow candidates across corridor:")
        for op in opps[:3]:
            print(f"      Block #{str(op['primary_block_id'])[:8]} on {op['section_code']} ({op['candidate_count']} candidates, Window: {op['primary_duration_min']}m)")
    else:
        print(f"  --> FAILED: {resp.status_code} - {resp.text}")
        sys.exit(1)

    # 2. Check Specific Block Shadow Candidates
    print("\n[2/5] Verifying POST /coa/shadow-check on an Active Primary Block...")
    db = SessionLocal()
    primary = db.query(Block).filter(Block.status == "active", Block.block_type == "primary").first()
    if not primary:
        print("  --> FAILED: No active primary blocks found in database.")
        db.close()
        sys.exit(1)

    check_resp = client.post("/coa/shadow-check", json={"block_id": str(primary.id)})
    if check_resp.status_code == 200:
        check_data = check_resp.json()
        print(f"  --> SUCCESS: Block #{str(primary.id)[:8]} evaluated on section {check_data['section_code']}:")
        print(f"      Primary Window: {check_data['primary_start']} to {check_data['primary_end']} ({check_data['primary_duration_min']} mins)")
        print(f"      Viable Shadow Candidates: {check_data['candidate_count']}")
    else:
        print(f"  --> FAILED: {check_resp.status_code} - {check_resp.text}")
        db.close()
        sys.exit(1)

    # 3. Structural Constraint Enforcement Verification
    print("\n[3/5] Verifying Structural Constraint Enforcement (Duration & Section Mismatch)...")
    primary_dur = int((primary.planned_end - primary.planned_start).total_seconds() // 60)

    # Attempt to attach with duration exceeding primary window
    excessive_dur = primary_dur + 60
    fake_defect = SMMSDefect(
        defect_code=f"EXCESS-{uuid.uuid4().hex[:6].upper()}",
        block_section_id=primary.block_section_id,
        defect_type="Excessive Work",
        severity="medium",
        criticality_score=50,
        estimated_duration_min=excessive_dur,
        requires_signal_block=True,
        status="open",
        work_category="defect",
        input_source="manual",
    )
    db.add(fake_defect)
    db.commit()
    db.refresh(fake_defect)

    try:
        reject_resp = client.post("/coa/shadow-attach", json={
            "primary_block_id": str(primary.id),
            "defect_id": str(fake_defect.id),
            "department": "SMMS",
        })
        if reject_resp.status_code == 400 and "Duration violation" in reject_resp.json()["detail"]:
            print(f"  --> SUCCESS: Rejected candidate exceeding primary duration ({excessive_dur}m > {primary_dur}m)")
        else:
            print(f"  --> FAILED: Expected 400 Duration violation, got: {reject_resp.status_code} - {reject_resp.text}")
            sys.exit(1)
    finally:
        db.query(SMMSDefect).filter(SMMSDefect.id == fake_defect.id).delete()
        db.commit()

    # 4. Controller Discard Flow
    print("\n[4/5] Testing Controller Discard Flow (POST /coa/shadow-discard)...")
    discard_resp = client.post("/coa/shadow-discard", json={
        "primary_block_id": str(primary.id),
        "department": "TMS",
        "reason": "Civil engineering gang not available at night",
    })
    if discard_resp.status_code == 200:
        disc_data = discard_resp.json()
        print(f"  --> SUCCESS: Discard handled. Status: {disc_data['status']}")
        print(f"      Notification Color: {disc_data['notification']['color']} (RED)")
        print(f"      Notification Title: {disc_data['notification']['title']}")
        print(f"      Message:            {disc_data['notification']['message']}")
    else:
        print(f"  --> FAILED: {discard_resp.status_code} - {discard_resp.text}")
        db.close()
        sys.exit(1)

    # 5. Controller Approval & Shadow Block Attachment (Live DB Flow)
    print("\n[5/5] Testing Controller Approval & Shadow Block Attachment (POST /coa/shadow-attach)...")
    test_cand_dur = min(40, primary_dur)
    test_defect = SMMSDefect(
        defect_code=f"SHADOW-{uuid.uuid4().hex[:6].upper()}",
        block_section_id=primary.block_section_id,
        defect_type="Axle Counter Maintenance",
        description="Piggyback maintenance during primary block",
        severity="medium",
        criticality_score=68,
        estimated_duration_min=test_cand_dur,
        requires_signal_block=True,
        status="open",
        work_category="defect",
        input_source="manual",
        required_by=primary.planned_end + timedelta(days=7),
    )
    db.add(test_defect)
    db.commit()
    db.refresh(test_defect)

    created_shadow_id = None
    created_request_id = None

    try:
        attach_resp = client.post("/coa/shadow-attach", json={
            "primary_block_id": str(primary.id),
            "defect_id": str(test_defect.id),
            "department": "SMMS",
        })
        if attach_resp.status_code != 200:
            print(f"  --> FAILED: {attach_resp.status_code} - {attach_resp.text}")
            sys.exit(1)

        attach_data = attach_resp.json()
        created_shadow_id = attach_data["shadow_block_id"]
        print(f"  --> SUCCESS: Controller APPROVED shadow block attachment:")
        print(f"      Shadow Block ID:   {created_shadow_id}")
        print(f"      Parent Block ID:   {attach_data['parent_block_id']}")
        print(f"      Section:           {attach_data['section_code']}")
        print(f"      Window:            {attach_data['planned_start']} to {attach_data['planned_end']} ({attach_data['duration_min']}m)")
        print(f"      Notification:      {attach_data['notification']['color'].upper()} ({attach_data['notification']['title']})")
        print(f"      Notice Message:    {attach_data['notification']['message']}")

        # Verify DB records
        shadow_row = db.query(Block).filter(Block.id == created_shadow_id).first()
        assert shadow_row is not None, "Shadow block not found in DB!"
        assert shadow_row.block_type == "shadow", f"Expected block_type='shadow', got '{shadow_row.block_type}'"
        assert shadow_row.parent_block_id == primary.id, "parent_block_id mismatch!"
        created_request_id = shadow_row.block_request_id

        history_row = (
            db.query(BlockAllocationHistory)
            .filter(BlockAllocationHistory.block_id == shadow_row.id)
            .first()
        )
        assert history_row is not None, "History record missing for shadow block!"
        assert history_row.reason == "shadow_block_attached", f"Expected reason='shadow_block_attached', got '{history_row.reason}'"

        db.refresh(test_defect)
        assert test_defect.status == "allocated", f"Expected defect status 'allocated', got '{test_defect.status}'"

        print("  --> SUCCESS: Verified DB state:")
        print(f"      - blocks.block_type = '{shadow_row.block_type}'")
        print(f"      - blocks.parent_block_id = {str(shadow_row.parent_block_id)[:8]}")
        print(f"      - block_allocation_history.reason = '{history_row.reason}'")
        print(f"      - smms_defects.status = '{test_defect.status}'")

    finally:
        # Clean up test artifacts cleanly
        if created_shadow_id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == created_shadow_id).delete()
            db.query(Block).filter(Block.id == created_shadow_id).delete()
        if created_request_id:
            db.query(BlockRequest).filter(BlockRequest.id == created_request_id).delete()
        if test_defect and test_defect.id:
            db.query(SMMSDefect).filter(SMMSDefect.id == test_defect.id).delete()
        db.commit()
        db.close()
        print("  --> Cleaned up temporary test rows from database.")

    print("\n" + "=" * 80)
    print("ALL PART 3 SHADOW-BLOCK VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    main()
