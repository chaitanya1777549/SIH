"""
Unit and integration tests for Part 1:
- Supabase connectivity & health check
- COA stations & block sections endpoints
- COA trains & blocks endpoints
- Department defects endpoints (TMS, SMMS, TDMS)
- Defect creation & validation
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "SIH26027" in data["project"]
    assert data["status"] == "online"

def test_health_check_supabase():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert data["database"]["status"] == "healthy"
    assert data["database"]["counts"]["stations"] == 12
    assert data["database"]["counts"]["block_sections"] == 22
    assert data["database"]["counts"]["trains"] > 0

def test_get_stations():
    response = client.get("/coa/stations")
    assert response.status_code == 200
    stations = response.json()
    assert len(stations) == 12
    # Verify corridor order
    assert stations[0]["station_code"] == "VSKP"
    assert stations[-1]["station_code"] == "BZA"
    sequences = [s["sequence_on_corridor"] for s in stations]
    assert sequences == sorted(sequences)

def test_get_block_sections():
    response = client.get("/coa/sections")
    assert response.status_code == 200
    sections = response.json()
    assert len(sections) == 22
    first = sections[0]
    assert "section_code" in first
    assert "from_station_code" in first
    assert "to_station_code" in first
    assert "track_code" in first

def test_get_trains_for_date():
    response = client.get("/coa/trains?date=2026-09-04")
    assert response.status_code == 200
    trains = response.json()
    assert len(trains) > 0
    sample = trains[0]
    assert "train_number" in sample
    assert "section_code" in sample
    assert "forecast_entry" in sample
    assert "forecast_exit" in sample

def test_get_blocks():
    response = client.get("/coa/blocks")
    assert response.status_code == 200
    blocks = response.json()
    assert isinstance(blocks, list)
    if len(blocks) > 0:
        sample = blocks[0]
        assert "planned_start" in sample
        assert "planned_end" in sample
        assert "duration_min" in sample
        assert "block_type" in sample
        assert sample["block_type"] in ["primary", "shadow"]

def test_get_department_defects():
    for dept in ["TMS", "SMMS", "TDMS"]:
        response = client.get(f"/departments/{dept}/defects")
        assert response.status_code == 200
        defects = response.json()
        assert isinstance(defects, list)
        if len(defects) > 0:
            sample = defects[0]
            assert sample["department"] == dept
            assert "defect_code" in sample
            assert "severity" in sample
            assert "criticality_score" in sample
            assert "requires_block" in sample

def test_create_defect_validation_error():
    # Attempt to create with invalid section UUID
    invalid_payload = {
        "block_section_id": "00000000-0000-0000-0000-000000000000",
        "defect_type": "Rail Crack Test",
        "estimated_duration_min": 60,
        "severity": "high"
    }
    response = client.post("/departments/TMS/defects", json=invalid_payload)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]
