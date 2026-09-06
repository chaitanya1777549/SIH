"""
Machine Learning Criticality Scoring Service (Phase C).
Provides explainable, data-driven criticality rankings based on corridor traffic density,
defect recurrence, urgency, severity, and track-block requirement.
"""
from backend.ml.scorer import predict_criticality, score_new_defect, CriticalityScoreResult

__all__ = ["predict_criticality", "score_new_defect", "CriticalityScoreResult"]
