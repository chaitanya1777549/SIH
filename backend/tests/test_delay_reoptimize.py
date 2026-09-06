"""
Tests for Dynamic Train Delay Propagation and Corridor Re-Optimization.
Verifies downstream propagation, conflict detection, high-criticality train diversion,
low-criticality block revocation, shadow/gap rescheduling, and department notification feeds.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database import get_db, SessionLocal
from backend.models import (
    Train,
    Station,
    BlockSection,
    TrainSchedule,
    Block,
    BlockRequest,
    TMSDefect,
    BlockAllocationHistory,
)
from backend.reoptimizer.engine import clear_notifications

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_notifications():
    clear_notifications()
    yield
    clear_notifications()

def test_propagate_train_delay_downstream():
    """
    Test propagating delay starting from AKP station for Train 12717 on 2026-09-05.
    Downstream sections should reflect the delay, while upstream sections remain unaffected.
    """
    db: Session = SessionLocal()
    try:
        # Reset any existing delay for clean test state
        train = db.query(Train).filter(Train.train_number == "12717").first()
        assert train is not None, "Seed train 12717 must exist"

        db.query(TrainSchedule).filter(
            TrainSchedule.train_id == train.id,
            TrainSchedule.service_date == date(2026, 9, 5)
        ).update({
            "delay_minutes": 0,
            "forecast_entry": TrainSchedule.scheduled_entry,
            "forecast_exit": TrainSchedule.scheduled_exit,
            "status": "scheduled"
        })
        db.commit()

        # Send delay update: +30 min at AKP
        response = client.post(
            "/coa/trains/update-delay",
            json={
                "train_number": "12717",
                "service_date": "2026-09-05",
                "station_code": "AKP",
                "delay_minutes": 30,
            }
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert data["delay_minutes"] == 30
        assert data["reported_station"] == "AKP"
        assert data["updated_sections_count"] > 0

        # Verify DB state: downstream sections have delay=30, upstream have delay=0
        scheds = (
            db.query(TrainSchedule)
            .join(BlockSection)
            .filter(
                TrainSchedule.train_id == train.id,
                TrainSchedule.service_date == date(2026, 9, 5)
            )
            .order_by(TrainSchedule.scheduled_entry.asc())
            .all()
        )

        # First section is BZA-EE-UP (upstream of AKP)
        first_sched = scheds[0]
        assert first_sched.delay_minutes == 0

        # Section containing AKP or downstream (e.g. AKP-DVD-UP)
        akp_dvd_sched = next((s for s in scheds if s.block_section.section_code == "AKP-DVD-UP"), None)
        assert akp_dvd_sched is not None
        assert akp_dvd_sched.delay_minutes == 30
        assert akp_dvd_sched.forecast_entry == akp_dvd_sched.scheduled_entry + timedelta(minutes=30)
    finally:
        db.close()


def test_conflict_resolution_high_criticality_diverts_train():
    """
    When a train delay causes conflict with a High-Criticality block (score >= 70),
    the safety block must be preserved and the conflicting train must be diverted.
    """
    db: Session = SessionLocal()
    try:
        service_date = date(2026, 9, 15) # test horizon
        section = db.query(BlockSection).filter(BlockSection.section_code == "AKP-TUNI-DN").first()
        assert section is not None

        train = db.query(Train).first()
        assert train is not None

        # Clean existing test schedules on this date
        db.query(TrainSchedule).filter(
            TrainSchedule.block_section_id == section.id,
            TrainSchedule.service_date == service_date
        ).delete()

        # Create a high-criticality TMS defect
        test_defect = TMSDefect(
            defect_code=f"TEST-CRIT-{uuid4().hex[:6].upper()}",
            block_section_id=section.id,
            defect_type="Rail Fracture",
            severity="critical",
            criticality_score=95,
            required_by=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
            estimated_duration_min=90,
            requires_track_block=True,
            status="allocated"
        )
        db.add(test_defect)
        db.flush()

        test_request = BlockRequest(
            source_system="TMS",
            tms_defect_id=test_defect.id,
            block_section_id=section.id,
            criticality_score=95,
            required_by=test_defect.required_by,
            estimated_duration_min=90,
            status="allocated",
            requires_power_block=False,
            requires_signal_block=False
        )
        db.add(test_request)
        db.flush()

        block_start = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
        block_end = datetime(2026, 9, 15, 9, 30, tzinfo=timezone.utc)

        test_block = Block(
            block_request_id=test_request.id,
            block_section_id=section.id,
            planned_start=block_start,
            planned_end=block_end,
            status="active",
            block_type="primary"
        )
        db.add(test_block)
        db.flush()

        # Create conflicting train schedule in same window (8:15 to 8:45)
        test_sched = TrainSchedule(
            train_id=train.id,
            block_section_id=section.id,
            service_date=service_date,
            scheduled_entry=datetime(2026, 9, 15, 7, 15, tzinfo=timezone.utc),
            scheduled_exit=datetime(2026, 9, 15, 7, 45, tzinfo=timezone.utc),
            forecast_entry=datetime(2026, 9, 15, 8, 15, tzinfo=timezone.utc), # delayed into block!
            forecast_exit=datetime(2026, 9, 15, 8, 45, tzinfo=timezone.utc),
            delay_minutes=60,
            status="scheduled"
        )
        db.add(test_sched)
        db.commit()

        # Run re-optimization
        response = client.post(
            "/coa/reoptimize",
            json={
                "service_date": "2026-09-15",
                "section_code": "AKP-TUNI-DN",
                "criticality_threshold": 70
            }
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert data["conflicts_detected"] == 1
        assert data["trains_diverted_count"] == 1
        assert data["blocks_revoked_count"] == 0

        detail = data["details"][0]
        assert detail["decision"] == "train_diverted"
        assert detail["criticality_score"] == 95

        # Check DB state: train is marked 'diverted' and block remains 'active'
        db.refresh(test_sched)
        db.refresh(test_block)
        assert test_sched.status == "diverted"
        assert test_block.status == "active"

    finally:
        # Cleanup test entities
        db.rollback()
        db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == test_block.id).delete()
        db.delete(test_block)
        db.delete(test_sched)
        db.delete(test_request)
        db.delete(test_defect)
        db.commit()
        db.close()


def test_conflict_resolution_low_criticality_revokes_and_reschedules():
    """
    When a train delay conflicts with a routine block (score < 70),
    the block must be revoked, audit history recorded, and rescheduled to a free gap.
    """
    db: Session = SessionLocal()
    try:
        service_date = date(2026, 9, 16)
        section = db.query(BlockSection).filter(BlockSection.section_code == "DVD-AKP-DN").first()
        assert section is not None

        train = db.query(Train).first()
        assert train is not None

        # Clean existing test schedules on this date
        db.query(TrainSchedule).filter(
            TrainSchedule.block_section_id == section.id,
            TrainSchedule.service_date == service_date
        ).delete()

        # Create a routine/low-criticality defect
        test_defect = TMSDefect(
            defect_code=f"TEST-ROUT-{uuid4().hex[:6].upper()}",
            block_section_id=section.id,
            defect_type="Cess Cleaning",
            severity="low",
            criticality_score=35,
            required_by=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
            estimated_duration_min=60,
            requires_track_block=True,
            status="allocated"
        )
        db.add(test_defect)
        db.flush()

        test_request = BlockRequest(
            source_system="TMS",
            tms_defect_id=test_defect.id,
            block_section_id=section.id,
            criticality_score=35,
            required_by=test_defect.required_by,
            estimated_duration_min=60,
            status="allocated",
            requires_power_block=False,
            requires_signal_block=False
        )
        db.add(test_request)
        db.flush()

        block_start = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)
        block_end = datetime(2026, 9, 16, 11, 0, tzinfo=timezone.utc)

        test_block = Block(
            block_request_id=test_request.id,
            block_section_id=section.id,
            planned_start=block_start,
            planned_end=block_end,
            status="active",
            block_type="primary"
        )
        db.add(test_block)
        db.flush()

        # Create conflicting train schedule in same window (10:15 to 10:45)
        test_sched = TrainSchedule(
            train_id=train.id,
            block_section_id=section.id,
            service_date=service_date,
            scheduled_entry=datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc),
            scheduled_exit=datetime(2026, 9, 16, 9, 45, tzinfo=timezone.utc),
            forecast_entry=datetime(2026, 9, 16, 10, 15, tzinfo=timezone.utc), # delayed into block
            forecast_exit=datetime(2026, 9, 16, 10, 45, tzinfo=timezone.utc),
            delay_minutes=60,
            status="scheduled"
        )
        db.add(test_sched)
        db.commit()

        # Run re-optimization
        response = client.post(
            "/coa/reoptimize",
            json={
                "service_date": "2026-09-16",
                "section_code": "DVD-AKP-DN",
                "criticality_threshold": 70
            }
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert data["conflicts_detected"] == 1
        assert data["blocks_revoked_count"] == 1

        detail = data["details"][0]
        assert "block_revoked" in detail["decision"]

        # Check DB state: original block is cancelled
        db.refresh(test_block)
        assert test_block.status == "cancelled"

        # Check audit history has reason 'reoptimized_due_to_delay'
        hist = db.query(BlockAllocationHistory).filter(
            BlockAllocationHistory.block_request_id == test_request.id,
            BlockAllocationHistory.reason == "reoptimized_due_to_delay"
        ).first()
        assert hist is not None

        # Check department received RED notification
        notifs_resp = client.get("/departments/TMS/notifications")
        assert notifs_resp.status_code == 200
        tms_notifs = notifs_resp.json()
        assert any(n["type"] == "RED" for n in tms_notifs)

    finally:
        # Cleanup
        db.rollback()
        # Find any rescheduled blocks
        rescheduled_blocks = db.query(Block).filter(Block.block_request_id == test_request.id).all()
        for b in rescheduled_blocks:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == b.id).delete()
            db.delete(b)
        db.delete(test_sched)
        db.delete(test_request)
        db.delete(test_defect)
        db.commit()
        db.close()


def test_one_click_delay_and_reoptimize_endpoint():
    """
    Test the combined one-click COA controller endpoint:
    /coa/trains/delay-and-reoptimize
    """
    response = client.post(
        "/coa/trains/delay-and-reoptimize",
        json={
            "train_number": "12717",
            "service_date": "2026-09-05",
            "station_code": "AKP",
            "delay_minutes": 15,
            "criticality_threshold": 70
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert "delay_update" in data
    assert "reoptimization" in data
    assert data["delay_update"]["delay_minutes"] == 15
