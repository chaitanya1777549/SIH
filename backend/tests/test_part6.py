"""
Automated unit & integration test suite for Part 6:
Natural Language & Voice Defect Intake (Section 7 of Brief).
Tests:
1. Deterministic corridor kilometer chainage matching (zero hallucination).
2. Deterministic station-pair and directional matching.
3. Constrained defect extraction (LLM & heuristic fallback).
4. Audio transcription (Whisper large-v3 & mock fallback).
5. POST /departments/parse-defect endpoint with ML criticality preview.
6. POST /departments/voice-intake and POST /departments/voice-intake-and-parse endpoints.
7. End-to-end flow: NL report -> preview draft -> confirmation & DB creation with input_source='nl_intake'.
"""
import io
import wave
import struct
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import BlockSection, TMSDefect
from backend.nl_intake.corridor_matcher import CorridorLocationMatcher
from backend.nl_intake.extractor import DefectExtractor
from backend.nl_intake.transcriber import AudioTranscriber
from backend.nl_intake.service import NLDefectIntakeService

client = TestClient(app)

@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_synthetic_wav_bytes(duration_sec: float = 0.5) -> bytes:
    """Generates a small valid WAV file in memory for testing audio endpoints."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        num_frames = int(16000 * duration_sec)
        # 0.5s of low sine/silence
        wf.writeframes(struct.pack("<" + ("h" * num_frames), *([0] * num_frames)))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test 1: Deterministic Corridor Kilometer Chainage Matching
# ---------------------------------------------------------------------------
def test_deterministic_chainage_km_matching(db_session):
    matcher = CorridorLocationMatcher(db_session)

    test_chainages = [
        ("km 10", "VSKP-DVD-DN", "DN"),
        ("km 25.4", "DVD-AKP-DN", "DN"),
        ("km 52", "AKP-TUNI-DN", "DN"),
        ("km 105", "TUNI-ANV-DN", "DN"),
        ("km 124/8", "ANV-SLO-DN", "DN"),     # Telegraph post notation 124.8 km
        ("km 165", "SLO-APT-DN", "DN"),
        ("km 185", "APT-RJY-DN", "DN"),
        ("km 210", "RJY-NDD-DN", "DN"),
        ("km 235", "NDD-TDD-DN", "DN"),
        ("km 260", "TDD-EE-DN", "DN"),
        ("km 315", "EE-BZA-DN", "DN"),
    ]

    for text_snip, expected_section, expected_dir in test_chainages:
        res = matcher.match_location(db_session, f"Defect detected at {text_snip}")
        assert res.section_code == expected_section, f"Failed matching {text_snip}: got {res.section_code}"
        assert res.direction == expected_dir
        assert res.match_method == "chainage_km"
        assert res.confidence >= 0.90
        assert res.block_section_id is not None


# ---------------------------------------------------------------------------
# Test 2: Directional and Station-Pair Matching
# ---------------------------------------------------------------------------
def test_station_pair_and_direction_matching(db_session):
    matcher = CorridorLocationMatcher(db_session)

    # Down line station pair
    res_dn = matcher.match_location(db_session, "Track irregularity between Anakapalle and Tuni down line.")
    assert res_dn.section_code == "AKP-TUNI-DN"
    assert res_dn.direction == "DN"
    assert res_dn.match_method == "station_pair"

    # Up line station pair
    res_up = matcher.match_location(db_session, "Point machine failure between Tuni and Annavaram on UP line.")
    assert res_up.section_code == "ANV-TUNI-UP"
    assert res_up.direction == "UP"
    assert res_up.match_method == "station_pair"

    # Direct section code
    res_code = matcher.match_location(db_session, "Emergency maintenance on AKP-TUNI-DN.")
    assert res_code.section_code == "AKP-TUNI-DN"
    assert res_code.confidence == 1.0
    assert res_code.match_method == "direct_code"

    # Directional route from origin towards destination
    res_dir = matcher.match_location(db_session, "Track defect outside Rajahmundry towards Vijayawada.")
    assert res_dir.section_code == "RJY-NDD-DN"
    assert res_dir.direction == "DN"


# ---------------------------------------------------------------------------
# Test 3: Constrained Defect Extraction
# ---------------------------------------------------------------------------
def test_defect_extractor_schemas():
    extractor = DefectExtractor()

    # TMS Report
    text_tms = "Observed severe rail fracture near Anakapalle towards Tuni around km 52, needs urgent 90 minute block before 4 PM."
    tms_res = extractor.extract_structured_defect(text_tms, department_hint="TMS")
    assert tms_res["department"] == "TMS"
    assert "rail fracture" in tms_res["defect_type"].lower()
    assert tms_res["severity"] in ["critical", "high"]
    assert tms_res["estimated_duration_min"] == 90
    assert tms_res["requires_track_block"] is True

    # SMMS Report
    text_smms = "Point machine failure at Samalkot yard, points not reversing, technician needs 120 minutes."
    smms_res = extractor.extract_structured_defect(text_smms, department_hint="SMMS")
    assert smms_res["department"] == "SMMS"
    assert "point machine" in smms_res["defect_type"].lower()
    assert smms_res["requires_signal_block"] is True

    # TDMS Report
    text_tdms = "OHE catenary wire sag noticed at km 124 near Annavaram, 60 minute power block required."
    tdms_res = extractor.extract_structured_defect(text_tdms, department_hint="TDMS")
    assert tdms_res["department"] == "TDMS"
    assert any(w in tdms_res["defect_type"].lower() for w in ["catenary", "ohe", "wire"])
    assert tdms_res["requires_power_block"] is True


# ---------------------------------------------------------------------------
# Test 4: Audio Transcription Module
# ---------------------------------------------------------------------------
def test_audio_transcriber_execution():
    transcriber = AudioTranscriber()
    wav_bytes = create_synthetic_wav_bytes(duration_sec=0.25)
    res = transcriber.transcribe_audio_bytes(wav_bytes, filename="test_sample.wav")
    assert "transcription" in res
    assert res["status"] in ["success", "simulated"]
    assert len(res["transcription"]) > 0


# ---------------------------------------------------------------------------
# Test 5: POST /departments/parse-defect Endpoint (with ML Criticality Preview)
# ---------------------------------------------------------------------------
def test_parse_defect_endpoint():
    payload = {
        "text": "Severe rail fracture detected at km 52 between Anakapalle and Tuni, needs urgent 90 minute block.",
        "department": "TMS"
    }
    response = client.post("/departments/parse-defect", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    # Draft defect attributes
    draft = data["draft_defect"]
    assert draft["department"] == "TMS"
    assert draft["section_code"] == "AKP-TUNI-DN"
    assert draft["severity"] in ["critical", "high"]
    assert draft["estimated_duration_min"] == 90
    assert draft["input_source"] == "nl_intake"
    assert draft["criticality_score"] >= 0 and draft["criticality_score"] <= 100

    # Location match verification
    loc = data["location_match"]
    assert loc["section_code"] == "AKP-TUNI-DN"
    assert loc["from_station_code"] == "AKP"
    assert loc["to_station_code"] == "TUNI"
    assert loc["confidence"] >= 0.90

    # ML Criticality verification (Phase C integration)
    crit = data["preview_criticality"]
    assert "predicted_score" in crit
    assert "features" in crit
    assert "feature_contributions" in crit
    assert "justification" in crit
    assert len(crit["justification"]) > 0


# ---------------------------------------------------------------------------
# Test 6: POST /departments/voice-intake & /departments/voice-intake-and-parse
# ---------------------------------------------------------------------------
def test_voice_intake_endpoints():
    wav_bytes = create_synthetic_wav_bytes(duration_sec=0.25)

    # 1. Test voice-intake transcription endpoint
    response = client.post(
        "/departments/voice-intake",
        files={"file": ("sample_report.wav", wav_bytes, "audio/wav")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "transcription" in data
    assert data["audio_filename"] == "sample_report.wav"

    # 2. Test 1-click voice-intake-and-parse endpoint
    response_full = client.post(
        "/departments/voice-intake-and-parse",
        files={"file": ("sample_report.wav", wav_bytes, "audio/wav")},
        data={"department": "TMS"}
    )
    assert response_full.status_code == 200
    full_data = response_full.json()
    assert full_data["status"] == "success"
    assert "draft_defect" in full_data
    assert "location_match" in full_data
    assert "preview_criticality" in full_data
    assert full_data["draft_defect"]["input_source"] == "voice"


# ---------------------------------------------------------------------------
# Test 7: End-to-End Flow: NL Preview -> User Confirm -> DB Defect Creation
# ---------------------------------------------------------------------------
def test_end_to_end_preview_and_confirm_defect_creation(db_session):
    # Step 1: Operator submits unstructured report to preview
    parse_resp = client.post(
        "/departments/parse-defect",
        json={
            "text": "Weld defect noticed at km 124 between Annavaram and Samalkot, needs 60 min block today.",
            "department": "TMS"
        }
    )
    assert parse_resp.status_code == 200
    preview_data = parse_resp.json()
    draft = preview_data["draft_defect"]

    # Step 2: Operator reviews preview and confirms creation
    create_payload = {
        "defect_code": f"TMS-TEST-NL-{draft['section_code'][:4]}",
        "block_section_id": draft["block_section_id"],
        "defect_type": draft["defect_type"],
        "description": draft["description"],
        "severity": draft["severity"],
        "criticality_score": draft["criticality_score"],
        "required_by": draft["required_by"],
        "estimated_duration_min": draft["estimated_duration_min"],
        "work_category": draft["work_category"],
        "input_source": draft["input_source"],
        "raw_report_text": draft["raw_report_text"],
        "requires_block": draft["requires_block"],
    }

    create_resp = client.post(f"/departments/{draft['department']}/defects", json=create_payload)
    assert create_resp.status_code in [200, 201], f"Defect creation failed: {create_resp.text}"
    created_defect = create_resp.json()

    assert created_defect["defect_code"] == create_payload["defect_code"]
    assert created_defect["block_section_id"] == draft["block_section_id"]
    assert created_defect["criticality_score"] == draft["criticality_score"]

    # Step 3: Verify record in PostgreSQL database
    db_record = db_session.query(TMSDefect).filter(TMSDefect.defect_code == create_payload["defect_code"]).first()
    assert db_record is not None
    assert db_record.input_source == "nl_intake"
    assert db_record.raw_report_text == create_payload["raw_report_text"]

    # Step 4: Cleanup test fixture
    db_session.delete(db_record)
    db_session.commit()
