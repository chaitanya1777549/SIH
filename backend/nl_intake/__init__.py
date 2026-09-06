"""
Natural Language and Voice Defect Intake Module for Visakhapatnam-Vijayawada Corridor.
"""
from backend.nl_intake.corridor_matcher import CorridorLocationMatcher, LocationMatchResult
from backend.nl_intake.transcriber import AudioTranscriber
from backend.nl_intake.extractor import DefectExtractor
from backend.nl_intake.service import NLDefectIntakeService

__all__ = [
    "CorridorLocationMatcher",
    "LocationMatchResult",
    "AudioTranscriber",
    "DefectExtractor",
    "NLDefectIntakeService",
]
