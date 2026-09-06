"""
Audio Transcription Service using Whisper large-v3 via Groq Free Tier API.
Converts spoken operator voice reports into high-fidelity text.
"""
import io
import os
import logging
from typing import Optional, Dict, Any
from groq import Groq

logger = logging.getLogger(__name__)

DEFAULT_WHISPER_MODEL = "whisper-large-v3"
FALLBACK_WHISPER_MODEL = "whisper-large-v3-turbo"

class AudioTranscriber:
    """
    Transcribes railway operator voice reports using Whisper large-v3 on Groq.
    Provides automatic fallback to turbo model or local test simulation if offline.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self._client: Optional[Groq] = None
        if self.api_key:
            try:
                self._client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client for Whisper: {e}")

    def is_available(self) -> bool:
        return self._client is not None

    def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "voice_report.wav",
        language: Optional[str] = None,
        prompt: Optional[str] = "Indian Railways track, signal, and OHE maintenance defect report",
    ) -> Dict[str, Any]:
        """
        Transcribes raw audio bytes into text using Whisper large-v3.
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValueError("Audio payload is empty.")

        if not self._client:
            # Fallback mode for offline testing / missing API key
            logger.info("GROQ_API_KEY not configured or offline; returning mock transcription.")
            return {
                "transcription": "Urgent rail fracture observed near Anakapalle towards Tuni at km 52. Requires immediate 90 minute track block.",
                "detected_language": "en",
                "audio_filename": filename,
                "model_used": "mock-whisper-fallback",
                "status": "simulated",
            }

        # Call Groq Whisper API
        last_error = None
        for model_name in [DEFAULT_WHISPER_MODEL, FALLBACK_WHISPER_MODEL]:
            try:
                bio = io.BytesIO(audio_bytes)
                bio.name = filename
                
                kwargs: Dict[str, Any] = {
                    "file": (filename, bio),
                    "model": model_name,
                    "response_format": "verbose_json",
                }
                if prompt:
                    kwargs["prompt"] = prompt
                if language:
                    kwargs["language"] = language

                resp = self._client.audio.transcriptions.create(**kwargs)
                
                transcription_text = resp.text if hasattr(resp, "text") else str(resp)
                detected_lang = getattr(resp, "language", language or "en")
                
                logger.info(f"Successfully transcribed audio ({len(audio_bytes)} bytes) using {model_name}.")
                return {
                    "transcription": transcription_text.strip(),
                    "detected_language": detected_lang,
                    "audio_filename": filename,
                    "model_used": model_name,
                    "status": "success",
                }
            except Exception as e:
                logger.warning(f"Whisper transcription failed with model {model_name}: {e}")
                last_error = e

        # If both models fail, raise clean descriptive exception
        raise RuntimeError(f"Groq Whisper transcription failed: {str(last_error)}")
