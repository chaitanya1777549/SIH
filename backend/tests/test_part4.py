"""
Unit and integration tests for Part 4: Explainable ML Criticality Scoring Service (Phase C).
Tests feature extraction, domain baseline formula, synthetic data generation,
GradientBoosting model inference, explainability breakdowns, preview-score endpoint,
and live automatic scoring on defect creation.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database import SessionLocal
from backend.models import BlockSection, TMSDefect
from backend.ml.feature_extractor import (
    encode_severity,
    compute_urgency_score,
    get_section_traffic_density,
    get_section_recurrence_score,
    extract_defect_features,
    calculate_domain_formula_score,
)
from backend.ml.scorer import predict_criticality, score_new_defect, CriticalityScoreResult
from backend.ml.train import generate_synthetic_dataset

client = TestClient(app)

def test_encode_severity():
    """Verify categorical severity encoding to standard scale."""
    assert encode_severity("critical") == 95.0
    assert encode_severity("high") == 75.0
    assert encode_severity("medium") == 50.0
    assert encode_severity("low") == 25.0
    assert encode_severity(None) == 50.0

def test_compute_urgency_score():
    """Verify time-to-deadline urgency scoring."""
    now = datetime.now(timezone.utc)
    # <= 12h
    assert compute_urgency_score(now + timedelta(hours=6), reference_time=now) == 100.0
    # <= 24h
    assert compute_urgency_score(now + timedelta(hours=18), reference_time=now) == 85.0
    # <= 48h
    assert compute_urgency_score(now + timedelta(hours=36), reference_time=now) == 70.0
    # <= 96h
    assert compute_urgency_score(now + timedelta(hours=72), reference_time=now) == 50.0
    # > 96h
    assert compute_urgency_score(now + timedelta(hours=120), reference_time=now) == 25.0
    # No deadline
    assert compute_urgency_score(None, reference_time=now) == 30.0

def test_extract_defect_features_from_db():
    """Verify live corridor feature extraction against real section."""
    db: Session = SessionLocal()
    try:
        section = db.query(BlockSection).first()
        assert section is not None
        
        feats = extract_defect_features(
            db=db,
            block_section_id=section.id,
            severity="critical",
            required_by=datetime.now(timezone.utc) + timedelta(hours=8),
            requires_block=True,
        )
        assert feats["severity_score"] == 95.0
        assert feats["urgency_score"] == 100.0
        assert 50.0 <= feats["traffic_density"] <= 100.0
        assert feats["recurrence_score"] >= 15.0
        assert feats["block_required_score"] == 100.0
    finally:
        db.close()

def test_synthetic_data_generation():
    """Verify synthetic dataset generator shapes and label boundaries."""
    X, y = generate_synthetic_dataset(n_samples=100, noise_std=2.0, random_state=123)
    assert X.shape == (100, 5)
    assert y.shape == (100,)
    assert bool((y >= 1.0).all() and (y <= 100.0).all())

def test_predict_criticality_explainability():
    """Verify inference returns full explainability structure."""
    features = {
        "severity_score": 95.0,
        "urgency_score": 100.0,
        "traffic_density": 90.0,
        "recurrence_score": 75.0,
        "block_required_score": 100.0,
    }
    result: CriticalityScoreResult = predict_criticality(features)
    assert 80 <= result.predicted_score <= 100
    assert result.dominant_factor in features
    assert "Defect Severity" in result.explanation or "Critical" in result.explanation
    assert sum(result.feature_contributions.values()) == pytest.approx(100.0, abs=0.5)

def test_preview_defect_score_endpoint():
    """Verify POST /departments/{dept}/defects/preview-score endpoint."""
    db: Session = SessionLocal()
    try:
        section = db.query(BlockSection).first()
        assert section is not None
        
        response = client.post(
            "/departments/TMS/defects/preview-score",
            json={
                "block_section_id": str(section.id),
                "severity": "critical",
                "required_by": (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat(),
                "requires_block": True,
                "work_category": "defect"
            }
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert "section_code" in data
        
        expl = data["explainability"]
        assert 70 <= expl["predicted_score"] <= 100
        assert "feature_values" in expl
        assert "feature_contributions" in expl
        assert "dominant_factor" in expl
        assert "explanation" in expl
    finally:
        db.close()

def test_create_defect_auto_scoring():
    """Verify that omitting criticality_score triggers ML auto-scoring."""
    db: Session = SessionLocal()
    defect_id = None
    try:
        section = db.query(BlockSection).first()
        assert section is not None
        
        # Omit criticality_score
        response = client.post(
            "/departments/TMS/defects",
            json={
                "defect_code": f"TMS-AUTO-{uuid4().hex[:6].upper()}",
                "block_section_id": str(section.id),
                "defect_type": "Weld Crack",
                "description": "Auto-scored weld crack",
                "severity": "high",
                "required_by": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                "estimated_duration_min": 90,
                "requires_block": True,
                "work_category": "defect",
                "input_source": "manual"
            }
        )
        assert response.status_code in (200, 201), response.text
        data = response.json()
        defect_id = data["id"]
        
        # Verify ML assigned a realistic non-zero score
        assert 50 <= data["criticality_score"] <= 95
        
    finally:
        if defect_id:
            db.query(TMSDefect).filter(TMSDefect.id == defect_id).delete()
            db.commit()
        db.close()
