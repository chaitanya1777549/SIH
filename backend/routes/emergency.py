"""
Emergency Mode routes for COA Controller and Department Interfaces (Section 6 & Phase D).
Provides:
- Incident intake & live conflict analysis
- Heuristic action recommendation (Hold / Divert / Block / Notify)
- Multi-option block comparison cards with real calculated trade-offs
- Controller decision confirmation with atomic emergency block creation
- Safety release and corridor reopening lifecycle
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import EmergencyIncident, BlockSection
from backend.schemas import (
    EmergencyIncidentCreateSchema,
    EmergencyAnalysisResponseSchema,
    EmergencyOptionCardSchema,
    EmergencyConfirmRequestSchema,
    EmergencyConfirmResponseSchema,
    EmergencyLifecycleAdvanceRequestSchema,
    EmergencyIncidentResponseSchema,
)
from backend.emergency.engine import (
    create_emergency_incident,
    determine_heuristic_recommendation,
    generate_emergency_block_options,
    confirm_emergency_decision,
    advance_incident_lifecycle,
)

router = APIRouter(prefix="/coa/emergency", tags=["Emergency Mode"])


@router.post("/incidents", response_model=EmergencyAnalysisResponseSchema)
def report_emergency_incident(
    payload: EmergencyIncidentCreateSchema,
    db: Session = Depends(get_db)
):
    """
    Report an emergency track/signal/power incident.
    Instantly runs corridor conflict analysis and returns recommended action + candidate block options.
    """
    incident = create_emergency_incident(
        db=db,
        source_system=payload.source_system.value,
        block_section_id=payload.block_section_id,
        reported_text=payload.reported_text,
        defect_id=payload.defect_id,
        defect_type=payload.defect_type,
        severity=payload.severity.value if payload.severity else "critical",
        estimated_duration_min=payload.estimated_duration_min,
    )

    section = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()
    rec_action, rec_reason = determine_heuristic_recommendation(db, incident)
    options = generate_emergency_block_options(db, incident, required_duration_min=payload.estimated_duration_min)

    return EmergencyAnalysisResponseSchema(
        status="success",
        incident_id=incident.id,
        source_system=incident.source_system,
        section_code=section.section_code if section else "UNKNOWN",
        incident_status=incident.status,
        recommended_action=rec_action,
        recommendation_reason=rec_reason,
        options=[EmergencyOptionCardSchema(**o) for o in options],
    )


@router.get("/incidents", response_model=List[EmergencyIncidentResponseSchema])
def list_emergency_incidents(
    status: Optional[str] = Query(None, description="Filter by status (reported, action_recommended, confirmed, released)"),
    db: Session = Depends(get_db)
):
    """
    Lists all emergency incidents on the corridor.
    """
    query = (
        db.query(EmergencyIncident)
        .options(joinedload(EmergencyIncident.block_section))
        .order_by(EmergencyIncident.created_at.desc())
    )
    if status:
        query = query.filter(EmergencyIncident.status == status)

    incidents = query.all()
    results = []
    for inc in incidents:
        res = EmergencyIncidentResponseSchema(
            id=inc.id,
            source_system=inc.source_system,
            block_section_id=inc.block_section_id,
            section_code=inc.block_section.section_code if inc.block_section else None,
            reported_text=inc.reported_text,
            status=inc.status,
            recommended_action=inc.recommended_action,
            controller_decision=inc.controller_decision,
            block_request_id=inc.block_request_id,
            confirmed_at=inc.confirmed_at,
            created_at=inc.created_at,
        )
        results.append(res)
    return results


@router.get("/incidents/{incident_id}", response_model=EmergencyAnalysisResponseSchema)
def get_emergency_incident_analysis(
    incident_id: UUID = Path(..., description="UUID of emergency incident"),
    db: Session = Depends(get_db)
):
    """
    Retrieves full analysis and real-time block option cards for an active incident.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"EmergencyIncident '{incident_id}' not found")

    section = db.query(BlockSection).filter(BlockSection.id == incident.block_section_id).first()
    rec_action, rec_reason = determine_heuristic_recommendation(db, incident)
    options = generate_emergency_block_options(db, incident)

    return EmergencyAnalysisResponseSchema(
        status="success",
        incident_id=incident.id,
        source_system=incident.source_system,
        section_code=section.section_code if section else "UNKNOWN",
        incident_status=incident.status,
        recommended_action=rec_action,
        recommendation_reason=rec_reason,
        options=[EmergencyOptionCardSchema(**o) for o in options],
    )


@router.post("/incidents/{incident_id}/confirm", response_model=EmergencyConfirmResponseSchema)
def confirm_incident_action(
    incident_id: UUID = Path(..., description="UUID of emergency incident"),
    payload: EmergencyConfirmRequestSchema = ...,
    db: Session = Depends(get_db)
):
    """
    Controller confirms the action decision:
    - If 'block': Atomically allocates the selected option card as an emergency Block.
    - If 'hold' / 'divert' / 'notify': Initiates operational directives and notifies concerned departments.
    """
    res = confirm_emergency_decision(
        db=db,
        incident_id=incident_id,
        decision=payload.decision,
        selected_option_id=payload.selected_option_id,
        notes=payload.notes,
    )
    return EmergencyConfirmResponseSchema(**res)


@router.post("/incidents/{incident_id}/advance")
def advance_incident_status(
    incident_id: UUID = Path(..., description="UUID of emergency incident"),
    payload: EmergencyLifecycleAdvanceRequestSchema = ...,
    db: Session = Depends(get_db)
):
    """
    Advances incident through repair, safety confirmation, and formal corridor release.
    """
    return advance_incident_lifecycle(
        db=db,
        incident_id=incident_id,
        target_status=payload.target_status,
        officer_notes=payload.notes,
    )
