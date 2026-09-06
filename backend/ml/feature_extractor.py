"""
Feature extraction engine for ML Criticality Scoring.
Extracts real-time domain features from the corridor database:
1. Severity score (domain-encoded: low=25, medium=50, high=75, critical=95)
2. Urgency score (derived from time-to-deadline: <=12h:100, <=24h:85, <=48h:70, <=96h:50, >96h:25)
3. Section traffic density (derived from real train_schedule volume across the corridor)
4. Section defect recurrence (count of active defects across all departments on this section)
5. Block requirement flag (100 if track/signal/power block required, 20 if off-track work)
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.models import TMSDefect, SMMSDefect, TDMSDefect, BlockSection, TrainSchedule

# Feature names in fixed order for the ML model
FEATURE_NAMES = [
    "severity_score",
    "urgency_score",
    "traffic_density",
    "recurrence_score",
    "block_required_score",
]

# Baseline weights for the explainable formula
DOMAIN_WEIGHTS = {
    "severity_score": 0.35,
    "urgency_score": 0.25,
    "traffic_density": 0.20,
    "recurrence_score": 0.10,
    "block_required_score": 0.10,
}

# In-memory caches to minimize remote Supabase latency
_TRAFFIC_DENSITY_CACHE: Dict[str, float] = {}
_MAX_SECTION_SCHEDULE_COUNT: Optional[int] = None

def encode_severity(severity: Optional[str]) -> float:
    """Encodes categorical severity into numeric scale."""
    if not severity:
        return 50.0
    sev = severity.lower()
    mapping = {
        "critical": 95.0,
        "high": 75.0,
        "medium": 50.0,
        "low": 25.0,
    }
    return mapping.get(sev, 50.0)

def compute_urgency_score(
    required_by: Optional[datetime],
    reference_time: Optional[datetime] = None
) -> float:
    """Computes urgency scale (1-100) based on hours remaining until required_by."""
    if not required_by:
        return 30.0  # Routine baseline when no deadline is set
    
    if not reference_time:
        reference_time = datetime.now(timezone.utc)
    
    if required_by.tzinfo is None:
        required_by = required_by.replace(tzinfo=timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
        
    diff_hours = (required_by - reference_time).total_seconds() / 3600.0
    
    if diff_hours <= 12:
        return 100.0
    elif diff_hours <= 24:
        return 85.0
    elif diff_hours <= 48:
        return 70.0
    elif diff_hours <= 96:
        return 50.0
    else:
        return 25.0

def get_section_traffic_density(db: Session, block_section_id: UUID) -> float:
    """
    Computes normalized section traffic density [0, 100] using real train_schedule counts.
    Caches results across the corridor for sub-millisecond lookups.
    """
    global _MAX_SECTION_SCHEDULE_COUNT, _TRAFFIC_DENSITY_CACHE
    sec_key = str(block_section_id)
    
    if sec_key in _TRAFFIC_DENSITY_CACHE:
        return _TRAFFIC_DENSITY_CACHE[sec_key]
        
    # Populate cache for all sections in one fast aggregated query
    rows = db.execute(text("""
        SELECT block_section_id, count(id) as cnt
        FROM train_schedule
        GROUP BY block_section_id;
    """)).fetchall()
    
    if not rows:
        return 50.0
        
    max_count = max(r[1] for r in rows) if rows else 1
    _MAX_SECTION_SCHEDULE_COUNT = max_count
    
    for r in rows:
        bs_id, count = str(r[0]), r[1]
        normalized = (count / max_count) * 100.0
        _TRAFFIC_DENSITY_CACHE[bs_id] = round(normalized, 2)
        
    return _TRAFFIC_DENSITY_CACHE.get(sec_key, 75.0)

def get_section_recurrence_score(db: Session, block_section_id: UUID) -> float:
    """
    Computes recurrence score based on the number of open/unresolved defects
    across TMS, SMMS, and TDMS on the specified section.
    """
    tms_cnt = db.query(TMSDefect).filter(
        TMSDefect.block_section_id == block_section_id,
        TMSDefect.status.in_(["open", "requested"])
    ).count()
    
    smms_cnt = db.query(SMMSDefect).filter(
        SMMSDefect.block_section_id == block_section_id,
        SMMSDefect.status.in_(["open", "requested"])
    ).count()
    
    tdms_cnt = db.query(TDMSDefect).filter(
        TDMSDefect.block_section_id == block_section_id,
        TDMSDefect.status.in_(["open", "requested"])
    ).count()
    
    total_open = tms_cnt + smms_cnt + tdms_cnt
    
    # Non-linear scaling: 0 defects -> 15.0, 1 -> 35.0, 2 -> 55.0, 3 -> 75.0, 4+ -> 95.0
    if total_open == 0:
        return 15.0
    elif total_open == 1:
        return 35.0
    elif total_open == 2:
        return 55.0
    elif total_open == 3:
        return 75.0
    else:
        return min(100.0, 75.0 + (total_open - 3) * 10.0)

def encode_block_required(requires_block: bool) -> float:
    """100 if block is required to perform maintenance safely, 20 if off-track."""
    return 100.0 if requires_block else 20.0

def extract_defect_features(
    db: Session,
    block_section_id: UUID,
    severity: Optional[str],
    required_by: Optional[datetime],
    requires_block: bool,
    detected_at: Optional[datetime] = None,
) -> Dict[str, float]:
    """
    Extracts the complete 5-feature vector for criticality prediction.
    """
    return {
        "severity_score": encode_severity(severity),
        "urgency_score": compute_urgency_score(required_by, reference_time=detected_at),
        "traffic_density": get_section_traffic_density(db, block_section_id),
        "recurrence_score": get_section_recurrence_score(db, block_section_id),
        "block_required_score": encode_block_required(requires_block),
    }

def calculate_domain_formula_score(features: Dict[str, float]) -> float:
    """
    Calculates the explicit domain baseline formula score:
    score = 0.35 * severity + 0.25 * urgency + 0.20 * traffic_density + 0.10 * recurrence + 0.10 * block_required
    """
    score = 0.0
    for feat_name, weight in DOMAIN_WEIGHTS.items():
        score += weight * features.get(feat_name, 50.0)
    return round(score, 2)
