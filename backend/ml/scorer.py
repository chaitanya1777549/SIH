"""
Explainable inference service for ML Criticality Scoring (Phase C).
Provides transparent, data-driven score predictions along with feature contribution breakdowns
and human-readable operational justifications.
"""
import os
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
import joblib

from sqlalchemy.orm import Session

from backend.ml.feature_extractor import (
    FEATURE_NAMES,
    DOMAIN_WEIGHTS,
    extract_defect_features,
    calculate_domain_formula_score,
)

logger = logging.getLogger("backend.ml.scorer")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "criticality_model.joblib")

_LOADED_ARTIFACT: Optional[Dict[str, Any]] = None

@dataclass
class CriticalityScoreResult:
    predicted_score: int
    formula_score: float
    feature_values: Dict[str, float]
    feature_contributions: Dict[str, float]
    feature_importances: Dict[str, float]
    dominant_factor: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_score": self.predicted_score,
            "formula_score": self.formula_score,
            "feature_values": self.feature_values,
            "feature_contributions": self.feature_contributions,
            "feature_importances": self.feature_importances,
            "dominant_factor": self.dominant_factor,
            "explanation": self.explanation,
        }

def get_or_load_model() -> Optional[Dict[str, Any]]:
    """Loads and caches the trained ML model artifact."""
    global _LOADED_ARTIFACT
    if _LOADED_ARTIFACT is not None:
        return _LOADED_ARTIFACT

    if os.path.exists(MODEL_PATH):
        try:
            _LOADED_ARTIFACT = joblib.load(MODEL_PATH)
            logger.info("Loaded trained criticality ML model from disk.")
            return _LOADED_ARTIFACT
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return None
    return None

def predict_criticality(features: Dict[str, float]) -> CriticalityScoreResult:
    """
    Predicts an explainable criticality score for a given feature dictionary.
    Falls back gracefully to the explicit domain baseline formula if model is missing.
    """
    formula_score = calculate_domain_formula_score(features)
    artifact = get_or_load_model()
    
    feature_vector = [features.get(name, 50.0) for name in FEATURE_NAMES]
    
    if artifact and "model" in artifact:
        model = artifact["model"]
        raw_pred = float(model.predict([feature_vector])[0])
        predicted_score = int(round(np.clip(raw_pred, 1.0, 100.0)))
        importances = artifact.get("feature_importances", {})
    else:
        # Graceful fallback to domain formula
        predicted_score = int(round(np.clip(formula_score, 1.0, 100.0)))
        importances = {k: round(w * 100, 2) for k, w in DOMAIN_WEIGHTS.items()}

    # Compute percentage contribution of each feature to the total score
    weighted_parts = {
        name: features.get(name, 50.0) * DOMAIN_WEIGHTS.get(name, 0.20)
        for name in FEATURE_NAMES
    }
    total_weighted = sum(weighted_parts.values()) if sum(weighted_parts.values()) > 0 else 1.0
    contributions = {
        name: round((val / total_weighted) * 100, 2)
        for name, val in weighted_parts.items()
    }

    # Identify dominant factor
    dominant_feat = max(contributions.items(), key=lambda x: x[1])[0]
    
    # Generate human-readable operational justification
    explanation = _generate_explanation_text(predicted_score, features, contributions, dominant_feat)

    return CriticalityScoreResult(
        predicted_score=predicted_score,
        formula_score=formula_score,
        feature_values={k: round(v, 2) for k, v in features.items()},
        feature_contributions=contributions,
        feature_importances=importances,
        dominant_factor=dominant_feat,
        explanation=explanation,
    )

def _generate_explanation_text(
    score: int,
    features: Dict[str, float],
    contributions: Dict[str, float],
    dominant: str
) -> str:
    """Generates plain-language domain explanation for railway controllers."""
    sev = features.get("severity_score", 50.0)
    urg = features.get("urgency_score", 30.0)
    dens = features.get("traffic_density", 75.0)
    rec = features.get("recurrence_score", 15.0)
    blk = features.get("block_required_score", 100.0)

    # Category label
    if score >= 75:
        level_str = "CRITICAL PRIORITY"
    elif score >= 50:
        level_str = "HIGH PRIORITY"
    elif score >= 35:
        level_str = "MEDIUM PRIORITY"
    else:
        level_str = "ROUTINE PRIORITY"

    dom_label_map = {
        "severity_score": "Defect Severity",
        "urgency_score": "Urgency / Near-Term Deadline",
        "traffic_density": "High Corridor Traffic Density",
        "recurrence_score": "Repeated Section Defect Density",
        "block_required_score": "Active Track-Block Safety Requirement",
    }
    dom_label = dom_label_map.get(dominant, dominant)
    dom_pct = contributions.get(dominant, 0.0)

    reasons = [f"Score {score}/100 ({level_str})"]
    reasons.append(f"Dominant factor: {dom_label} ({dom_pct:.1f}% contribution).")

    details = []
    if sev >= 75:
        details.append(f"elevated physical severity (score {sev:.0f})")
    if urg >= 70:
        details.append(f"near-term deadline requiring expedited resolution")
    if dens >= 85:
        details.append(f"high traffic density route")
    if rec >= 50:
        details.append(f"multiple active defects on this block section")
    if blk >= 80:
        details.append(f"requires full track/signal/power isolation")

    if details:
        reasons.append("Compounded by: " + ", ".join(details) + ".")

    return " ".join(reasons)

def score_new_defect(
    db: Session,
    block_section_id: Any,
    severity: Optional[str],
    required_by: Optional[Any],
    requires_block: bool,
    detected_at: Optional[Any] = None,
) -> CriticalityScoreResult:
    """
    High-level entrypoint to score a new defect using real database context.
    """
    features = extract_defect_features(
        db=db,
        block_section_id=block_section_id,
        severity=severity,
        required_by=required_by,
        requires_block=requires_block,
        detected_at=detected_at,
    )
    return predict_criticality(features)
