"""
Orchestration Service for Natural Language and Voice Defect Intake.
Glues Audio Transcription, Constrained LLM Extraction, Deterministic Corridor Matching,
and Phase C ML Criticality Scoring into a unified operator confirmation preview.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.nl_intake.transcriber import AudioTranscriber
from backend.nl_intake.extractor import DefectExtractor
from backend.nl_intake.corridor_matcher import CorridorLocationMatcher, LocationMatchResult
from backend.ml.scorer import score_new_defect, CriticalityScoreResult

logger = logging.getLogger(__name__)

class NLDefectIntakeService:
    """
    Unified Voice and Natural Language intake pipeline.
    Produces rich, fully explained preview drafts for operator verification before saving.
    """

    def __init__(self, db: Optional[Session] = None):
        self.transcriber = AudioTranscriber()
        self.extractor = DefectExtractor()
        self.matcher = CorridorLocationMatcher(db)

    def parse_text_to_preview(
        self,
        db: Session,
        text: str,
        department_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses raw text report -> extracts structured attributes -> matches corridor location
        -> computes ML criticality score preview -> returns operator confirmation card.
        """
        # 1. Constrained extraction (Groq LLM with fallback)
        extracted = self.extractor.extract_structured_defect(text, department_hint)
        dept = extracted["department"]
        
        # 2. Deterministic corridor location matching
        location_query = extracted.get("raw_location_text") or text
        default_dir = extracted.get("direction") or "DN"
        loc_res: LocationMatchResult = self.matcher.match_location(db, location_query, default_direction=default_dir)

        # 3. Calculate required_by timestamp
        urgency_hrs = extracted.get("urgency_hours", 24.0)
        now_utc = datetime.now(timezone.utc)
        required_by = now_utc + timedelta(hours=urgency_hrs)

        # 4. Determine block requirement flag
        requires_block = bool(
            extracted.get("requires_track_block") or
            extracted.get("requires_signal_block") or
            extracted.get("requires_power_block") or
            True
        )

        # 5. Compute ML criticality score preview (Phase C model)
        ml_score_res: CriticalityScoreResult = score_new_defect(
            db=db,
            block_section_id=loc_res.block_section_id,
            severity=extracted["severity"],
            required_by=required_by,
            requires_block=requires_block,
        )

        # 6. Assemble ready-to-submit defect create payload
        req_track = (dept == "TMS") and requires_block
        req_signal = (dept == "SMMS") and requires_block
        req_power = (dept == "TDMS") and requires_block

        draft_defect_payload = {
            "department": dept,
            "block_section_id": str(loc_res.block_section_id),
            "section_code": loc_res.section_code,
            "defect_type": extracted["defect_type"],
            "description": extracted["description"],
            "severity": extracted["severity"],
            "criticality_score": ml_score_res.predicted_score,
            "required_by": required_by.isoformat(),
            "estimated_duration_min": extracted["estimated_duration_min"],
            "work_category": extracted["work_category"],
            "input_source": "nl_intake",
            "raw_report_text": text.strip(),
            "requires_block": requires_block,
            "requires_track_block": req_track,
            "requires_signal_block": req_signal,
            "requires_power_block": req_power,
        }

        return {
            "status": "success",
            "draft_defect": draft_defect_payload,
            "location_match": loc_res.to_dict(),
            "preview_criticality": {
                "predicted_score": ml_score_res.predicted_score,
                "formula_baseline": ml_score_res.formula_score,
                "features": ml_score_res.feature_values,
                "feature_contributions": ml_score_res.feature_contributions,
                "dominant_factor": ml_score_res.dominant_factor,
                "justification": ml_score_res.explanation,
            },
            "extraction_metadata": {
                "extraction_method": extracted.get("extraction_method"),
                "urgency_hours": urgency_hrs,
                "raw_location_text": extracted.get("raw_location_text"),
            },
            "raw_text": text.strip(),
        }

    def transcribe_and_preview_audio(
        self,
        db: Session,
        audio_bytes: bytes,
        filename: str = "voice_report.wav",
        department_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribes audio report via Whisper large-v3 -> runs complete preview pipeline.
        """
        # 1. Transcribe audio
        transcription_res = self.transcriber.transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            filename=filename
        )
        transcribed_text = transcription_res["transcription"]

        # 2. Run full text-to-preview pipeline
        preview_res = self.parse_text_to_preview(
            db=db,
            text=transcribed_text,
            department_hint=department_hint
        )

        # 3. Attach audio transcription metadata
        preview_res["audio_transcription"] = {
            "transcription": transcribed_text,
            "detected_language": transcription_res.get("detected_language", "en"),
            "audio_filename": filename,
            "transcription_model": transcription_res.get("model_used"),
            "transcription_status": transcription_res.get("status"),
        }
        # Mark draft input_source as voice
        preview_res["draft_defect"]["input_source"] = "voice"

        return preview_res
