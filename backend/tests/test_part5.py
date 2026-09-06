"""
Unit and integration tests for Part 5: Emergency Mode Engine & Multi-Option Decision Matrix.
Tests incident intake, heuristic recommendation (Hold/Divert/Block/Notify),
sustainable time enforcement, candidate option cards, controller confirmation with emergency block creation,
and the safety confirmation / release lifecycle.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database import SessionLocal
from backend.models import (
    BlockSection,
    EmergencyIncident,
    Block,
    BlockRequest,
    BlockAllocationHistory,
    TMSDefect,
)
from backend.emergency.engine import generate_emergency_block_options

client = TestClient(app)

def test_report_emergency_incident_and_generate_options():
    """
    Verify reporting an emergency incident on a corridor block section.
    Should instantly run conflict analysis and return recommended action + candidate block options.
    """
    db: Session = SessionLocal()
    incident_id = None
    try:
        section = db.query(BlockSection).first()
        assert section is not None

        response = client.post(
            "/coa/emergency/incidents",
            json={
                "source_system": "TMS",
                "block_section_id": str(section.id),
                "reported_text": "Severe rail fracture observed at km 124/8. Immediate isolation required.",
                "defect_type": "Rail Fracture",
                "severity": "critical",
                "estimated_duration_min": 90,
            }
        )
        assert response.status_code == 200, response.text
        data = response.json()
        incident_id = data["incident_id"]

        assert data["status"] == "success"
        assert data["source_system"] == "TMS"
        assert data["section_code"] == section.section_code
        assert data["recommended_action"] in ("hold", "divert", "block", "notify")
        assert len(data["recommendation_reason"]) > 0

        # Verify candidate block options
        options = data["options"]
        assert len(options) >= 1
        immediate_opt = next((o for o in options if o["option_id"] == "opt-immediate"), None)
        assert immediate_opt is not None
        assert immediate_opt["duration_min"] == 90
        assert immediate_opt["sustainable"] is True
        assert "resource_impact" in immediate_opt

    finally:
        if incident_id:
            inc = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
            if inc:
                d_id = inc.tms_defect_id
                db.delete(inc)
                db.flush()
                if d_id:
                    db.query(TMSDefect).filter(TMSDefect.id == d_id).delete()
            db.commit()
        db.close()


def test_sustainable_time_disqualification_rule():
    """
    Verifies that candidate shadow blocks or gaps that start AFTER the emergency defect's
    sustainable deadline are strictly disqualified and never offered as viable options.
    """
    db: Session = SessionLocal()
    incident = None
    try:
        section = db.query(BlockSection).first()
        assert section is not None
        now = datetime.now(timezone.utc)

        # Create a test emergency defect that can only be sustained for 1 hour
        strict_deadline = now + timedelta(hours=1)
        defect = TMSDefect(
            defect_code=f"TMS-EMERG-STRICT-{uuid4().hex[:6].upper()}",
            block_section_id=section.id,
            defect_type="Broken Rail",
            severity="critical",
            criticality_score=98,
            required_by=strict_deadline,
            estimated_duration_min=90,
            requires_track_block=True,
            status="open",
        )
        db.add(defect)
        db.flush()

        incident = EmergencyIncident(
            source_system="TMS",
            tms_defect_id=defect.id,
            block_section_id=section.id,
            reported_text="Test strict sustainable deadline defect",
            status="action_recommended",
        )
        db.add(incident)
        db.commit()

        # Generate options
        options = generate_emergency_block_options(db, incident, required_duration_min=90, reference_time=now)

        # Every offered option must start on or before strict_deadline
        for opt in options:
            start_dt = datetime.fromisoformat(opt["planned_start"])
            assert start_dt <= strict_deadline + timedelta(minutes=1), (
                f"Option {opt['option_id']} starts at {start_dt} which exceeds sustainable deadline {strict_deadline}!"
            )

    finally:
        if incident:
            db.query(EmergencyIncident).filter(EmergencyIncident.id == incident.id).delete()
            db.query(TMSDefect).filter(TMSDefect.id == defect.id).delete()
            db.commit()
        db.close()


def test_controller_confirm_block_option_creates_emergency_block():
    """
    Test controller selecting a block option card:
    - Atomically creates BlockRequest with is_emergency=True.
    - Creates Block with status='active'.
    - Logs BlockAllocationHistory with reason='emergency_block_allocated'.
    - Updates incident status to 'confirmed'.
    """
    db: Session = SessionLocal()
    incident_id = None
    block_id = None
    req_id = None
    try:
        section = db.query(BlockSection).first()
        assert section is not None

        # 1. Report incident
        report_resp = client.post(
            "/coa/emergency/incidents",
            json={
                "source_system": "TMS",
                "block_section_id": str(section.id),
                "reported_text": "Emergency rail shear detected. Immediate closure needed.",
                "defect_type": "Rail Shear",
                "severity": "critical",
                "estimated_duration_min": 60,
            }
        )
        assert report_resp.status_code == 200
        incident_id = report_resp.json()["incident_id"]

        # 2. Controller confirms 'block' with Option 1 (Immediate)
        confirm_resp = client.post(
            f"/coa/emergency/incidents/{incident_id}/confirm",
            json={
                "decision": "block",
                "selected_option_id": "opt-immediate",
                "notes": "Authorized emergency track possession by Chief Controller.",
            }
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        confirm_data = confirm_resp.json()
        assert confirm_data["status"] == "success"
        assert confirm_data["decision"] == "block"
        block_id = confirm_data["block_id"]
        req_id = confirm_data["block_request_id"]

        # 3. Verify Database entities
        db_block = db.query(Block).filter(Block.id == block_id).first()
        assert db_block is not None
        assert db_block.status == "active"

        db_req = db.query(BlockRequest).filter(BlockRequest.id == req_id).first()
        assert db_req is not None
        assert db_req.is_emergency is True
        assert db_req.status == "allocated"

        db_hist = db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == block_id).first()
        assert db_hist is not None
        assert db_hist.reason == "emergency_block_allocated"

        # 4. Advance through repair and safety release lifecycle
        adv_resp1 = client.post(
            f"/coa/emergency/incidents/{incident_id}/advance",
            json={"target_status": "repairing"}
        )
        assert adv_resp1.status_code == 200

        adv_resp2 = client.post(
            f"/coa/emergency/incidents/{incident_id}/advance",
            json={"target_status": "safety_confirmed", "notes": "Ultrasonic rail test passed."}
        )
        assert adv_resp2.status_code == 200

        adv_resp3 = client.post(
            f"/coa/emergency/incidents/{incident_id}/advance",
            json={"target_status": "released", "notes": "Track cleared for traffic."}
        )
        assert adv_resp3.status_code == 200

        # Verify emergency block is now 'completed'
        db.refresh(db_block)
        assert db_block.status == "completed"

    finally:
        # Cleanup
        if block_id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == block_id).delete()
            db.query(Block).filter(Block.id == block_id).delete()
        if incident_id:
            inc = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
            if inc:
                d_id = inc.tms_defect_id
                inc.block_request_id = None
                db.flush()
                db.delete(inc)
                db.flush()
                if req_id:
                    db.query(BlockRequest).filter(BlockRequest.id == req_id).delete()
                if d_id:
                    db.query(TMSDefect).filter(TMSDefect.id == d_id).delete()
        db.commit()
        db.close()


def test_list_emergency_incidents_endpoint():
    """Verify GET /coa/emergency/incidents returns list."""
    response = client.get("/coa/emergency/incidents")
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
