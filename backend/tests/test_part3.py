"""
Unit and integration tests for Part 3:
- Shadow block candidate discovery and structural constraint enforcement
- POST /coa/shadow-check endpoint
- GET /coa/shadow-opportunities endpoint
- POST /coa/shadow-attach approval flow and transactional write-back
- POST /coa/shadow-discard decline flow and notification generation
"""
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
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
)

client = TestClient(app)

def test_shadow_check_invalid_block_id():
    fake_id = str(uuid.uuid4())
    resp = client.post("/coa/shadow-check", json={"block_id": fake_id})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]

def test_shadow_opportunities_endpoint():
    resp = client.get("/coa/shadow-opportunities")
    assert resp.status_code == 200
    opportunities = resp.json()
    assert isinstance(opportunities, list)
    for opp in opportunities:
        assert "primary_block_id" in opp
        assert "section_code" in opp
        assert "candidate_count" in opp
        assert opp["candidate_count"] > 0
        assert len(opp["candidates"]) == opp["candidate_count"]

def test_shadow_discard_flow():
    resp = client.post("/coa/shadow-discard", json={
        "primary_block_id": str(uuid.uuid4()),
        "department": "SMMS",
        "reason": "Signal team unavailable during this window",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "DISCARDED"
    assert "notification" in data
    assert data["notification"]["color"] == "red"
    assert data["notification"]["department"] == "SMMS"

def test_shadow_attach_end_to_end_flow():
    """
    Finds an existing primary block, creates a compliant test defect on the same section,
    verifies shadow candidate discovery, executes controller approval (shadow-attach),
    verifies child block and audit trail, and cleans up cleanly.
    """
    db = SessionLocal()
    test_defect = None
    created_shadow_block_id = None
    created_request_id = None

    try:
        # 1. Fetch an existing active primary block
        primary = db.query(Block).filter(Block.status == "active", Block.block_type == "primary").first()
        assert primary is not None, "No active primary block in DB to test against"

        primary_dur = int((primary.planned_end - primary.planned_start).total_seconds() // 60)
        assert primary_dur >= 30, "Primary block duration too short for test"

        # 2. Create a compliant test defect on the same section with duration <= primary_dur
        cand_dur = min(45, primary_dur)
        deadline = primary.planned_end + timedelta(days=5)

        test_defect = SMMSDefect(
            defect_code=f"SHADOW-{uuid.uuid4().hex[:6].upper()}",
            block_section_id=primary.block_section_id,
            defect_type="Signal Testing - Shadow Candidate",
            description="Piggyback testing on existing primary block",
            severity="medium",
            criticality_score=65,
            estimated_duration_min=cand_dur,
            requires_signal_block=True,
            status="open",
            work_category="defect",
            input_source="manual",
            required_by=deadline,
        )
        db.add(test_defect)
        db.commit()
        db.refresh(test_defect)

        # 3. Test POST /coa/shadow-check
        check_resp = client.post("/coa/shadow-check", json={"block_id": str(primary.id)})
        assert check_resp.status_code == 200
        check_data = check_resp.json()
        assert check_data["primary_block_id"] == str(primary.id)

        matching_cands = [c for c in check_data["candidates"] if c["defect_code"] == test_defect.defect_code]
        assert len(matching_cands) == 1, "Created test defect was not detected as a shadow candidate!"
        cand = matching_cands[0]
        assert cand["source_system"] == "SMMS"
        assert cand["estimated_duration_min"] == cand_dur
        assert cand["duration_fit_ratio"] <= 1.0

        # 4. Test Controller Approval via POST /coa/shadow-attach
        attach_resp = client.post("/coa/shadow-attach", json={
            "primary_block_id": str(primary.id),
            "defect_id": str(test_defect.id),
            "department": "SMMS",
        })
        assert attach_resp.status_code == 200
        attach_data = attach_resp.json()
        assert attach_data["status"] == "APPROVED"
        assert attach_data["parent_block_id"] == str(primary.id)
        assert attach_data["duration_min"] == cand_dur
        assert "notification" in attach_data
        assert attach_data["notification"]["color"] == "green"
        assert attach_data["notification"]["department"] == "SMMS"

        created_shadow_block_id = attach_data["shadow_block_id"]

        # 5. Verify Database State
        shadow_row = db.query(Block).filter(Block.id == created_shadow_block_id).first()
        assert shadow_row is not None
        assert shadow_row.block_type == "shadow"
        assert shadow_row.parent_block_id == primary.id
        assert shadow_row.status == "active"
        created_request_id = shadow_row.block_request_id

        # Verify audit history
        history_row = (
            db.query(BlockAllocationHistory)
            .filter(BlockAllocationHistory.block_id == shadow_row.id)
            .first()
        )
        assert history_row is not None
        assert history_row.reason == "shadow_block_attached"

        # Verify defect status mirrored to 'allocated'
        db.refresh(test_defect)
        assert test_defect.status == "allocated"

    finally:
        # Clean up test artifacts cleanly
        if created_shadow_block_id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == created_shadow_block_id).delete()
            db.query(Block).filter(Block.id == created_shadow_block_id).delete()
        if created_request_id:
            db.query(BlockRequest).filter(BlockRequest.id == created_request_id).delete()
        if test_defect and test_defect.id:
            db.query(SMMSDefect).filter(SMMSDefect.id == test_defect.id).delete()
        db.commit()
        db.close()
