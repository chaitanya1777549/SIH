"""
Department routes for TMS, SMMS, and TDMS defect management using SQLAlchemy.
Optimized with joinedload to eliminate N+1 query latency over Supabase.
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from sqlalchemy.orm import Session, joinedload
from backend.database import get_db
from backend.models import TMSDefect, SMMSDefect, TDMSDefect, BlockSection
from backend.schemas import (
    DepartmentCode,
    DefectCreateSchema,
    DefectResponseSchema,
    SeverityLevel,
    WorkCategory,
    DepartmentNotificationSchema,
    CriticalityExplainabilitySchema,
    DefectScorePreviewRequestSchema,
    DefectScorePreviewResponseSchema,
)
from backend.reoptimizer.engine import get_all_notifications
from backend.ml.scorer import score_new_defect

router = APIRouter(prefix="/departments", tags=["Departments"])

DEPT_MODEL_CONFIG = {
    DepartmentCode.TMS: (TMSDefect, "requires_track_block"),
    DepartmentCode.SMMS: (SMMSDefect, "requires_signal_block"),
    DepartmentCode.TDMS: (TDMSDefect, "requires_power_block"),
}

def _calculate_fallback_criticality(severity: str, category: str, requires_block: bool) -> int:
    base = {
        SeverityLevel.low: 25,
        SeverityLevel.medium: 50,
        SeverityLevel.high: 75,
        SeverityLevel.critical: 95,
    }.get(severity, 50)
    
    if category == WorkCategory.overdue_task:
        base += 10
    elif category == WorkCategory.scheduled_maintenance:
        base -= 5
        
    if requires_block:
        base += 5
        
    return max(1, min(100, base))

@router.get("/{dept}/defects", response_model=List[DefectResponseSchema])
def get_department_defects(
    dept: DepartmentCode = Path(..., description="Department code: TMS, SMMS, or TDMS"),
    status: Optional[str] = Query(None, description="Optional status filter: open, requested, allocated, resolved"),
    db: Session = Depends(get_db)
):
    """
    Retrieve all defect records for the specified department via SQLAlchemy,
    eager-loading block sections and stations in a single query.
    """
    Model, block_flag_attr = DEPT_MODEL_CONFIG[dept]
    
    query = (
        db.query(Model)
        .options(
            joinedload(Model.block_section).joinedload(BlockSection.from_station),
            joinedload(Model.block_section).joinedload(BlockSection.to_station),
        )
    )
    if status:
        query = query.filter(Model.status == status)
        
    records = query.order_by(Model.created_at.desc()).all()
    
    results = []
    for r in records:
        sec = r.block_section
        results.append(DefectResponseSchema(
            id=r.id,
            department=dept.value,
            defect_code=r.defect_code,
            block_section_id=r.block_section_id,
            section_code=sec.section_code if sec else None,
            from_station_code=sec.from_station.station_code if sec and sec.from_station else None,
            to_station_code=sec.to_station.station_code if sec and sec.to_station else None,
            defect_type=r.defect_type,
            description=r.description,
            severity=r.severity,
            criticality_score=r.criticality_score,
            detected_at=r.detected_at,
            required_by=r.required_by,
            estimated_duration_min=r.estimated_duration_min,
            requires_block=getattr(r, block_flag_attr),
            status=r.status,
            created_at=r.created_at,
            work_category=r.work_category,
            input_source=r.input_source,
            raw_report_text=r.raw_report_text,
        ))
    return results

@router.post("/{dept}/defects", response_model=DefectResponseSchema, status_code=201)
def create_department_defect(
    payload: DefectCreateSchema,
    dept: DepartmentCode = Path(..., description="Department code: TMS, SMMS, or TDMS"),
    db: Session = Depends(get_db)
):
    """
    Register a new defect report into the department's table in Supabase via SQLAlchemy.
    """
    Model, block_flag_attr = DEPT_MODEL_CONFIG[dept]
    
    # 1. Verify that the block section exists
    section = (
        db.query(BlockSection)
        .options(
            joinedload(BlockSection.from_station),
            joinedload(BlockSection.to_station),
        )
        .filter(BlockSection.id == payload.block_section_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=400, detail=f"Block section '{payload.block_section_id}' does not exist.")
        
    # 2. Determine defect code
    defect_code = payload.defect_code
    if not defect_code:
        short_id = uuid.uuid4().hex[:6].upper()
        defect_code = f"{dept.value}-{short_id}"
        
    # 3. Determine criticality score using explainable ML model
    score = payload.criticality_score
    if score is None:
        ml_res = score_new_defect(
            db=db,
            block_section_id=payload.block_section_id,
            severity=payload.severity.value,
            required_by=payload.required_by,
            requires_block=payload.requires_block,
        )
        score = ml_res.predicted_score
        
    input_source_val = payload.input_source.value
    if input_source_val == "voice":
        input_source_val = "nl_intake"

    kwargs = {
        "defect_code": defect_code,
        "block_section_id": payload.block_section_id,
        "defect_type": payload.defect_type,
        "description": payload.description,
        "severity": payload.severity.value,
        "criticality_score": score,
        "required_by": payload.required_by,
        "estimated_duration_min": payload.estimated_duration_min,
        block_flag_attr: payload.requires_block,
        "status": "open",
        "work_category": payload.work_category.value,
        "input_source": input_source_val,
        "raw_report_text": payload.raw_report_text,
    }
    
    defect = Model(**kwargs)
    db.add(defect)
    try:
        db.commit()
        db.refresh(defect)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to create defect: {str(e)}")

    return DefectResponseSchema(
        id=defect.id,
        department=dept.value,
        defect_code=defect.defect_code,
        block_section_id=defect.block_section_id,
        section_code=section.section_code,
        from_station_code=section.from_station.station_code if section.from_station else None,
        to_station_code=section.to_station.station_code if section.to_station else None,
        defect_type=defect.defect_type,
        description=defect.description,
        severity=defect.severity,
        criticality_score=defect.criticality_score,
        detected_at=defect.detected_at,
        required_by=defect.required_by,
        estimated_duration_min=defect.estimated_duration_min,
        requires_block=getattr(defect, block_flag_attr),
        status=defect.status,
        created_at=defect.created_at,
        work_category=defect.work_category,
        input_source=defect.input_source,
        raw_report_text=defect.raw_report_text,
    )


@router.post("/{dept}/defects/preview-score", response_model=DefectScorePreviewResponseSchema)
def preview_defect_criticality_score(
    dept: DepartmentCode = Path(..., description="Department code: TMS, SMMS, or TDMS"),
    payload: DefectScorePreviewRequestSchema = ...,
    db: Session = Depends(get_db)
):
    """
    Previews the ML criticality score and full explainability breakdown
    for a proposed defect before official submission.
    """
    section = db.query(BlockSection).filter(BlockSection.id == payload.block_section_id).first()
    if not section:
        raise HTTPException(status_code=400, detail=f"Block section '{payload.block_section_id}' does not exist.")
        
    ml_res = score_new_defect(
        db=db,
        block_section_id=payload.block_section_id,
        severity=payload.severity.value,
        required_by=payload.required_by,
        requires_block=payload.requires_block,
    )
    
    return DefectScorePreviewResponseSchema(
        status="success",
        section_code=section.section_code,
        explainability=CriticalityExplainabilitySchema(**ml_res.to_dict())
    )


@router.get("/{dept}/notifications", response_model=List[DepartmentNotificationSchema])
def get_department_notifications(
    dept: DepartmentCode = Path(..., description="Department code: TMS, SMMS, or TDMS"),
    limit: int = Query(50, ge=1, le=200, description="Max notifications to retrieve"),
):
    """
    Retrieve live notifications for this department (GREEN approvals/reschedules, RED revocations/delays).
    """
    return get_all_notifications(department=dept.value, limit=limit)

