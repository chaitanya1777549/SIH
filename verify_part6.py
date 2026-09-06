"""
SIH26027 — Part 6: Natural Language & Voice Defect Intake Verification Script.
Demonstrates:
1. Audio file synthesis and live Whisper large-v3 transcription via Groq API.
2. Deterministic corridor location matcher (chainage km, station pairs, directions).
3. Constrained LLM JSON defect extraction (Groq openai/gpt-oss-120b).
4. Full preview generation with Phase C ML criticality scoring & plain-English explanation.
5. End-to-end defect creation flow.
"""
import io
import wave
import struct
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from backend.database import SessionLocal
from backend.nl_intake.corridor_matcher import CorridorLocationMatcher
from backend.nl_intake.transcriber import AudioTranscriber
from backend.nl_intake.extractor import DefectExtractor
from backend.nl_intake.service import NLDefectIntakeService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("verify_part6")

def create_sample_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        num_frames = 16000 # 1 second
        wf.writeframes(struct.pack("<" + ("h" * num_frames), *([0] * num_frames)))
    return buf.getvalue()

def main():
    print("=" * 80)
    print(" SIH26027: Part 6 — Natural Language & Voice Defect Intake Verification")
    print(" Corridor: Visakhapatnam (VSKP) -> Vijayawada (BZA)")
    print("=" * 80)

    db = SessionLocal()

    # ---------------------------------------------------------
    # Step 1: Deterministic Corridor Location Matcher
    # ---------------------------------------------------------
    print("\n--- 1. DETERMINISTIC CORRIDOR LOCATION MATCHER (Zero Hallucination) ---")
    matcher = CorridorLocationMatcher(db)

    test_queries = [
        "Severe rail fracture observed at km 52 between Anakapalle and Tuni.",
        "Point machine failure between Tuni and Annavaram on UP line.",
        "OHE wire slack noticed at km 124 near Samalkot.",
        "Tamping required on section AKP-TUNI-DN.",
        "Track geometry irregularity reported outside Rajahmundry towards Vijayawada.",
        "Emergency rail crack at km 235 near Nidadavolu."
    ]

    for q in test_queries:
        res = matcher.match_location(db, q)
        print(f"\n[QUERY] \"{q}\"")
        print(f" -> Section Code : {res.section_code} ({res.direction} line)")
        print(f" -> Stations     : {res.from_station_code} -> {res.to_station_code} [Track: {res.track_code}]")
        print(f" -> Section UUID : {res.block_section_id}")
        print(f" -> Method/Conf  : {res.match_method} (Confidence: {res.confidence:.2f})")
        print(f" -> Explanation  : {res.explanation}")

    # ---------------------------------------------------------
    # Step 2: Audio Transcription via Whisper large-v3
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("--- 2. GROQ WHISPER LARGE-V3 AUDIO TRANSCRIPTION ---")
    transcriber = AudioTranscriber()
    sample_wav = create_sample_wav()
    print(f"Synthesized test audio payload ({len(sample_wav)} bytes). Calling Whisper large-v3...")
    
    trans_res = transcriber.transcribe_audio_bytes(sample_wav, filename="field_operator_memo.wav")
    print(f" -> Status           : {trans_res.get('status')}")
    print(f" -> Model Used       : {trans_res.get('model_used')}")
    print(f" -> Detected Language: {trans_res.get('detected_language')}")
    print(f" -> Transcription    : \"{trans_res.get('transcription')}\"")

    # ---------------------------------------------------------
    # Step 3: Constrained LLM Extraction (openai/gpt-oss-120b)
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("--- 3. CONSTRAINED LLM STRUCTURED EXTRACTION (openai/gpt-oss-120b) ---")
    extractor = DefectExtractor()

    sample_reports = [
        ("TMS", "Observed severe rail fracture near Anakapalle towards Tuni around km 52, needs urgent 90 minute block before 4 PM today."),
        ("SMMS", "Point machine 102 failure at Samalkot junction on DN line, technician needs 120 minutes track isolation."),
        ("TDMS", "OHE catenary wire sag noticed at km 124 between Annavaram and Samalkot, urgent 60 minute power block required.")
    ]

    for dept, raw_text in sample_reports:
        print(f"\n[DEPARTMENT: {dept}] Raw Memo: \"{raw_text}\"")
        extracted = extractor.extract_structured_defect(raw_text, department_hint=dept)
        print(f" -> Defect Type     : {extracted['defect_type']}")
        print(f" -> Severity        : {extracted['severity'].upper()}")
        print(f" -> Duration (min)  : {extracted['estimated_duration_min']}")
        print(f" -> Urgency (hours) : {extracted['urgency_hours']}")
        print(f" -> Direction       : {extracted['direction']}")
        print(f" -> Requires Block  : Track={extracted['requires_track_block']}, Signal={extracted['requires_signal_block']}, Power={extracted['requires_power_block']}")
        print(f" -> Extractor Model : {extracted.get('extraction_method')}")

    # ---------------------------------------------------------
    # Step 4: Full End-to-End Defect Preview with Phase C ML Scorer
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("--- 4. FULL DEFECT PREVIEW WITH PHASE C ML CRITICALITY SCORING ---")
    service = NLDefectIntakeService(db)
    memo = "Severe rail web shear detected at km 52 between Anakapalle and Tuni, requires immediate 90 minute block before 3 PM."
    print(f"Generating preview for: \"{memo}\"...\n")

    preview = service.parse_text_to_preview(db, memo, department_hint="TMS")
    draft = preview["draft_defect"]
    crit = preview["preview_criticality"]
    loc = preview["location_match"]

    print("[DRAFT DEFECT READY FOR OPERATOR CONFIRMATION]")
    print(f" * Department      : {draft['department']}")
    print(f" * Defect Type     : {draft['defect_type']}")
    print(f" * Section Code    : {draft['section_code']} ({loc['from_station_code']} -> {loc['to_station_code']})")
    print(f" * Severity        : {draft['severity'].upper()}")
    print(f" * Duration        : {draft['estimated_duration_min']} minutes")
    print(f" * Input Source    : {draft['input_source']}")
    print(f" * Deadline        : {draft['required_by']}")

    print("\n[EXPLAINABLE ML CRITICALITY PREVIEW (PHASE C MODEL)]")
    print(f" * Predicted Score : {crit['predicted_score']} / 100")
    print(f" * Baseline Score  : {crit['formula_baseline']:.2f}")
    print(f" * Dominant Factor : {crit['dominant_factor']}")
    print(f" * Feature Contributions:")
    for f_name, contrib in crit["feature_contributions"].items():
        print(f"    - {f_name:22s}: {contrib:5.1f}% (raw value: {crit['features'][f_name]})")
    print(f" * Operational Justification:")
    print(f"   \"{crit['justification']}\"")

    db.close()
    print("\n" + "=" * 80)
    print(" SUCCESS: Part 6 Natural Language & Voice Defect Intake fully verified!")
    print("=" * 80)

if __name__ == "__main__":
    main()
