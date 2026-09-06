"""
API Router for Voice and Natural Language Defect Intake (Part 6 / Section 7 of Brief).
Endpoints:
- POST /departments/voice-intake: Transcribe spoken audio via Whisper large-v3.
- POST /departments/parse-defect: Parse raw text into structured defect draft with matched section and ML criticality preview.
- POST /departments/voice-intake-and-parse: 1-click audio upload to structured defect preview.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    DepartmentCode,
    VoiceIntakeResponseSchema,
    DefectParseRequestSchema,
    DefectParsePreviewResponseSchema,
)
from backend.nl_intake.service import NLDefectIntakeService
from backend.nl_intake.transcriber import AudioTranscriber

logger = logging.getLogger("backend.routes.nl_intake")

router = APIRouter(prefix="/departments", tags=["Voice & Natural Language Defect Intake"])

@router.post(
    "/voice-intake",
    response_model=VoiceIntakeResponseSchema,
    summary="Transcribe Spoken Operator Voice Report via Whisper large-v3",
    description="Upload an audio recording (.wav, .mp3, .m4a, .webm, .ogg) to transcribe spoken defect report using Groq Whisper large-v3.",
)
async def transcribe_voice_endpoint(
    file: UploadFile = File(..., description="Audio file of operator speaking defect report."),
    prompt: Optional[str] = Form(None, description="Optional domain prompt for Whisper."),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No audio file uploaded.")

    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded audio file is empty.")

        transcriber = AudioTranscriber()
        result = transcriber.transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            filename=file.filename,
            prompt=prompt or "Indian Railways track, signal, and OHE maintenance defect report",
        )
        return VoiceIntakeResponseSchema(
            status=result.get("status", "success"),
            transcription=result["transcription"],
            detected_language=result.get("detected_language", "en"),
            audio_filename=file.filename,
            model_used=result.get("model_used", "whisper-large-v3"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Voice transcription error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Transcription failed: {str(e)}")


@router.post(
    "/parse-defect",
    response_model=DefectParsePreviewResponseSchema,
    summary="Parse Natural Language Text into Structured Defect Preview",
    description=(
        "Converts unstructured text into a fully qualified defect draft: extracts attributes using a constrained LLM, "
        "deterministically maps location text to an exact corridor block section (no LLM hallucination), "
        "and computes Phase C ML criticality score preview before operator confirms saving."
    ),
)
def parse_defect_text_endpoint(
    payload: DefectParseRequestSchema,
    db: Session = Depends(get_db),
):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input text cannot be empty.")

    try:
        service = NLDefectIntakeService(db)
        dept_hint = payload.department.value if payload.department else None
        preview = service.parse_text_to_preview(
            db=db,
            text=payload.text,
            department_hint=dept_hint,
        )
        return DefectParsePreviewResponseSchema(**preview)
    except Exception as e:
        logger.exception("Defect text parsing error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to parse defect text: {str(e)}")


@router.post(
    "/voice-intake-and-parse",
    response_model=DefectParsePreviewResponseSchema,
    summary="1-Click Audio Intake to Complete Defect Preview",
    description="Upload spoken audio, transcribe it via Whisper large-v3, extract structured attributes, match corridor section, and preview ML criticality score in a single call.",
)
async def voice_intake_and_parse_endpoint(
    file: UploadFile = File(..., description="Audio file recording of the defect report."),
    department: Optional[DepartmentCode] = Form(None, description="Optional reporting department hint (TMS, SMMS, TDMS)."),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No audio file uploaded.")

    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded audio file is empty.")

        service = NLDefectIntakeService(db)
        dept_hint = department.value if department else None
        preview = service.transcribe_and_preview_audio(
            db=db,
            audio_bytes=audio_bytes,
            filename=file.filename,
            department_hint=dept_hint,
        )
        return DefectParsePreviewResponseSchema(**preview)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Voice intake and parse error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Voice intake and parsing failed: {str(e)}")
