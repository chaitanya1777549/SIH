"""
Pydantic schemas for the AI-Powered Automatic Block Planning System.
Matches database_schema_reference.sql column definitions and constraints.
"""
from datetime import datetime, date, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

# --- Enums ---

class DepartmentCode(str, Enum):
    TMS = "TMS"    # Track Management System (Civil/Permanent Way)
    SMMS = "SMMS"  # Signal & Telecommunication
    TDMS = "TDMS"  # Traction Distribution (Electrical/OHE)

class SeverityLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class DefectStatus(str, Enum):
    open = "open"
    requested = "requested"
    allocated = "allocated"
    resolved = "resolved"

class WorkCategory(str, Enum):
    defect = "defect"
    scheduled_maintenance = "scheduled_maintenance"
    overdue_task = "overdue_task"

class InputSource(str, Enum):
    manual = "manual"
    nl_intake = "nl_intake"
    voice = "voice"
    emergency = "emergency"

class BlockType(str, Enum):
    primary = "primary"
    shadow = "shadow"

class BlockStatus(str, Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    superseded = "superseded"

class TrainStatus(str, Enum):
    scheduled = "scheduled"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


# --- Station & Section Schemas ---

class StationSchema(BaseModel):
    id: UUID
    station_code: str
    station_name: str
    sequence_on_corridor: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class BlockSectionSchema(BaseModel):
    id: UUID
    section_code: str
    from_station_id: UUID
    to_station_id: UUID
    from_station_code: Optional[str] = None
    from_station_name: Optional[str] = None
    to_station_code: Optional[str] = None
    to_station_name: Optional[str] = None
    track_id: UUID
    track_code: Optional[str] = None
    length_km: Optional[float] = None
    sequence_order: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Train & Train Schedule Schemas ---

class TrainMovementSchema(BaseModel):
    id: UUID
    train_id: UUID
    train_number: str
    train_name: Optional[str] = None
    train_type: Optional[str] = None
    block_section_id: UUID
    section_code: str
    sequence_order: int
    service_date: date
    scheduled_entry: datetime
    scheduled_exit: datetime
    forecast_entry: datetime
    forecast_exit: datetime
    delay_minutes: int
    status: str
    model_config = ConfigDict(from_attributes=True)


# --- Block & Allocation Schemas ---

class BlockDetailSchema(BaseModel):
    id: UUID
    block_request_id: UUID
    block_section_id: UUID
    section_code: str
    from_station_code: Optional[str] = None
    to_station_code: Optional[str] = None
    planned_start: datetime
    planned_end: datetime
    duration_min: int
    status: str
    block_type: str
    parent_block_id: Optional[UUID] = None
    source_system: Optional[str] = None
    defect_code: Optional[str] = None
    defect_type: Optional[str] = None
    criticality_score: Optional[int] = None
    optimization_run_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Defect Schemas ---

class DefectCreateSchema(BaseModel):
    defect_code: Optional[str] = Field(None, description="Optional custom defect code; auto-generated if omitted.")
    block_section_id: UUID = Field(..., description="UUID of the block section.")
    defect_type: str = Field(..., max_length=50, description="Type of defect (e.g., Rail Fracture, Signal Failure, OHE Sag).")
    description: Optional[str] = Field(None, description="Detailed description of the defect.")
    severity: SeverityLevel = Field(SeverityLevel.medium, description="Severity level.")
    criticality_score: Optional[int] = Field(None, ge=0, le=100, description="0-100 criticality score. If omitted, computed via ML/heuristics.")
    required_by: Optional[datetime] = Field(None, description="Deadline by which the maintenance/block must complete.")
    estimated_duration_min: int = Field(..., gt=0, description="Estimated duration in minutes required for repair.")
    work_category: WorkCategory = Field(WorkCategory.defect, description="Work category.")
    input_source: InputSource = Field(InputSource.manual, description="Input source (manual, nl_intake, emergency).")
    raw_report_text: Optional[str] = Field(None, description="Original report text if from voice or NL intake.")
    requires_block: bool = Field(True, description="Whether this defect requires a maintenance block.")

class DefectResponseSchema(BaseModel):
    id: UUID
    department: str
    defect_code: str
    block_section_id: UUID
    section_code: Optional[str] = None
    from_station_code: Optional[str] = None
    to_station_code: Optional[str] = None
    defect_type: str
    description: Optional[str] = None
    severity: str
    criticality_score: int
    detected_at: datetime
    required_by: Optional[datetime] = None
    estimated_duration_min: int
    requires_block: bool
    status: str
    created_at: datetime
    work_category: str
    input_source: str
    raw_report_text: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# --- Optimizer Schemas ---

class OptimizeRequestSchema(BaseModel):
    start_date: date = Field(..., description="Start date for the optimization horizon (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date for the optimization horizon (YYYY-MM-DD)")
    safety_buffer_min: int = Field(10, ge=0, le=60, description="Safety padding minutes before and after train occupancies")
    max_solve_time_sec: int = Field(30, ge=1, le=120, description="Maximum solver execution time in seconds")

class AllocationResultSchema(BaseModel):
    block_id: UUID
    block_request_id: UUID
    block_section_id: UUID
    section_code: str
    planned_start: datetime
    planned_end: datetime
    duration_min: int
    criticality_score: int
    source_system: str
    defect_code: Optional[str] = None
    defect_type: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class OptimizeResponseSchema(BaseModel):
    status: str
    horizon_start: datetime
    horizon_end: datetime
    total_pending_requests: int
    scheduled_count: int
    unscheduled_count: int
    total_criticality_scheduled: int
    allocations: List[AllocationResultSchema]
    unscheduled_request_ids: List[UUID]
    execution_time_ms: float


# --- Shadow Block Schemas ---

class ShadowCheckRequestSchema(BaseModel):
    block_id: UUID = Field(..., description="UUID of the primary block to evaluate for shadow attachment")

class ShadowCandidateSchema(BaseModel):
    candidate_type: str = Field(..., description="'block_request' or 'defect'")
    candidate_id: UUID
    block_request_id: Optional[UUID] = None
    defect_id: UUID
    source_system: str
    department: Optional[str] = None
    defect_code: str
    defect_type: str
    criticality_score: int
    estimated_duration_min: int
    required_by: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    duration_fit_ratio: float
    margin_before_deadline_hours: Optional[float] = None
    recommendation_reason: str

class ShadowCheckResponseSchema(BaseModel):
    primary_block_id: UUID
    block_section_id: UUID
    section_code: str
    from_station_code: Optional[str] = None
    to_station_code: Optional[str] = None
    primary_start: datetime
    primary_end: datetime
    primary_duration_min: int
    primary_source_system: Optional[str] = None
    primary_defect_code: Optional[str] = None
    candidate_count: int
    candidates: List[ShadowCandidateSchema]

class ShadowAttachRequestSchema(BaseModel):
    primary_block_id: UUID = Field(..., description="UUID of the target primary block")
    block_request_id: Optional[UUID] = Field(None, description="UUID of pending block request (if already created)")
    defect_id: Optional[UUID] = Field(None, description="UUID of open defect to attach directly")
    department: Optional[str] = Field(None, description="Department code: TMS, SMMS, or TDMS")
    source_system: Optional[str] = Field(None, description="Department code alias: TMS, SMMS, or TDMS")

class ShadowAttachResponseSchema(BaseModel):
    status: str
    shadow_block_id: UUID
    parent_block_id: UUID
    block_section_id: UUID
    section_code: str
    planned_start: datetime
    planned_end: datetime
    duration_min: int
    source_system: str
    defect_code: str
    message: str
    notification: Dict[str, Any]

class ShadowDiscardRequestSchema(BaseModel):
    primary_block_id: UUID
    defect_id: Optional[UUID] = None
    block_request_id: Optional[UUID] = None
    department: Optional[str] = None
    source_system: Optional[str] = None
    reason: Optional[str] = "Controller discarded shadow block proposal"

class ShadowDiscardResponseSchema(BaseModel):
    status: str
    message: str
    notification: Dict[str, Any]


# --- Health & Response Schemas ---

class HealthResponse(BaseModel):
    status: str
    database: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Dynamic Train Delay & Re-Optimization Schemas ---

class TrainDelayUpdateRequestSchema(BaseModel):
    train_number: str = Field(..., description="Train number, e.g. '12717'")
    service_date: date = Field(..., description="Service date (YYYY-MM-DD)")
    station_code: str = Field(..., description="Station code where delay is reported, e.g. 'AKP'")
    delay_minutes: int = Field(..., ge=0, description="Delay duration in minutes (e.g. 30)")

class SectionForecastUpdate(BaseModel):
    section_code: str
    from_station: str
    to_station: str
    scheduled_entry: datetime
    scheduled_exit: datetime
    forecast_entry: datetime
    forecast_exit: datetime
    delay_minutes: int
    status: str

class TrainDelayUpdateResponseSchema(BaseModel):
    status: str
    train_number: str
    service_date: date
    reported_station: str
    delay_minutes: int
    updated_sections_count: int
    updated_sections: List[SectionForecastUpdate]

class ReOptimizeRequestSchema(BaseModel):
    service_date: date = Field(..., description="Service date for re-optimization (YYYY-MM-DD)")
    section_code: Optional[str] = Field(None, description="Optional specific block section code (e.g. 'AKP-TUNI-DN')")
    criticality_threshold: int = Field(70, ge=0, le=100, description="Score threshold: >= threshold diverts train; < threshold revokes block and reschedules")

class ConflictResolutionDetailSchema(BaseModel):
    conflict_type: str
    section_code: str
    train_number: str
    train_forecast_entry: datetime
    train_forecast_exit: datetime
    block_id: UUID
    block_planned_start: datetime
    block_planned_end: datetime
    defect_code: Optional[str] = None
    defect_department: Optional[str] = None
    criticality_score: int
    severity: Optional[str] = None
    decision: str
    rescheduled_slot: Optional[Dict[str, Any]] = None
    notes: str

class DepartmentNotificationSchema(BaseModel):
    id: str
    timestamp: datetime
    department: str
    type: str
    title: str
    message: str
    defect_code: Optional[str] = None
    section_code: Optional[str] = None
    action_taken: str

class ReOptimizeResponseSchema(BaseModel):
    status: str
    service_date: date
    conflicts_detected: int
    trains_diverted_count: int
    blocks_revoked_count: int
    blocks_rescheduled_count: int
    details: List[ConflictResolutionDetailSchema]
    notifications: List[DepartmentNotificationSchema]

class DelayAndReoptimizeRequestSchema(BaseModel):
    train_number: str = Field(..., description="Train number, e.g. '12717'")
    service_date: date = Field(..., description="Service date (YYYY-MM-DD)")
    station_code: str = Field(..., description="Station code where delay is reported, e.g. 'AKP'")
    delay_minutes: int = Field(..., ge=0, description="Delay duration in minutes (e.g. 30)")
    criticality_threshold: int = Field(70, ge=0, le=100, description="Threshold for train diversion vs. maintenance revocation")


# --- ML Criticality Scoring & Explainability Schemas ---

class CriticalityExplainabilitySchema(BaseModel):
    predicted_score: int = Field(..., ge=1, le=100, description="Model predicted score (1-100)")
    formula_score: float = Field(..., description="Domain formula baseline score")
    feature_values: Dict[str, float] = Field(..., description="Extracted feature values")
    feature_contributions: Dict[str, float] = Field(..., description="Percentage contribution of each feature to the score")
    feature_importances: Dict[str, float] = Field(..., description="Trained model global feature importances")
    dominant_factor: str = Field(..., description="Feature that contributed most to this score")
    explanation: str = Field(..., description="Human-readable operational justification")

class DefectScorePreviewRequestSchema(BaseModel):
    block_section_id: UUID = Field(..., description="UUID of the block section")
    severity: SeverityLevel = Field(..., description="Defect severity (low, medium, high, critical)")
    required_by: Optional[datetime] = Field(None, description="Resolution deadline")
    requires_block: bool = Field(True, description="Whether track/signal/power block is required")
    work_category: Optional[WorkCategory] = Field(WorkCategory.defect, description="Work category")

class DefectScorePreviewResponseSchema(BaseModel):
    status: str
    section_code: str
    explainability: CriticalityExplainabilitySchema


# --- Emergency Mode Schemas ---

class EmergencyIncidentCreateSchema(BaseModel):
    source_system: DepartmentCode = Field(..., description="Reporting department: TMS, SMMS, or TDMS")
    block_section_id: UUID = Field(..., description="UUID of the damaged block section")
    reported_text: str = Field(..., description="Emergency incident description / field observation")
    defect_id: Optional[UUID] = Field(None, description="Optional existing defect UUID")
    defect_type: Optional[str] = Field(None, description="Type of defect, e.g. Rail Fracture, Signal Failure")
    severity: Optional[SeverityLevel] = Field(SeverityLevel.critical, description="Severity (defaults to critical)")
    estimated_duration_min: int = Field(90, ge=15, le=480, description="Estimated repair duration in minutes")

class EmergencyOptionCardSchema(BaseModel):
    option_id: str
    label: str
    planned_start: str
    planned_end: str
    duration_min: int
    trains_affected_count: int
    affected_train_numbers: List[str]
    total_delay_minutes: int
    is_shadow: bool
    parent_block_id: Optional[str] = None
    resource_impact: str
    sustainable: bool
    description: str

class EmergencyAnalysisResponseSchema(BaseModel):
    status: str
    incident_id: UUID
    source_system: str
    section_code: str
    incident_status: str
    recommended_action: str
    recommendation_reason: str
    options: List[EmergencyOptionCardSchema]

class EmergencyConfirmRequestSchema(BaseModel):
    decision: str = Field(..., description="'hold', 'divert', 'block', or 'notify'")
    selected_option_id: Optional[str] = Field(None, description="Selected block option ID (required if decision is 'block')")
    notes: Optional[str] = Field(None, description="Operational notes or reason")

class EmergencyConfirmResponseSchema(BaseModel):
    status: str
    incident_id: str
    decision: str
    confirmed_at: str
    block_id: Optional[str] = None
    block_request_id: Optional[str] = None
    message: str

class EmergencyLifecycleAdvanceRequestSchema(BaseModel):
    target_status: str = Field(..., description="'repairing', 'safety_confirmed', or 'released'")
    notes: Optional[str] = Field(None, description="Field or safety notes")

class EmergencyIncidentResponseSchema(BaseModel):
    id: UUID
    source_system: str
    block_section_id: UUID
    section_code: Optional[str] = None
    reported_text: str
    status: str
    recommended_action: Optional[str] = None
    controller_decision: Optional[str] = None
    block_request_id: Optional[UUID] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Voice & Natural Language Defect Intake Schemas (Part 6) ---

class VoiceIntakeResponseSchema(BaseModel):
    status: str
    transcription: str
    detected_language: str
    audio_filename: str
    model_used: str

class DefectParseRequestSchema(BaseModel):
    text: str = Field(..., description="Unstructured natural language defect report text (spoken or typed).")
    department: Optional[DepartmentCode] = Field(None, description="Optional reporting department hint (TMS, SMMS, TDMS).")

class LocationMatchSchema(BaseModel):
    block_section_id: UUID
    section_code: str
    from_station_code: str
    to_station_code: str
    track_code: str
    direction: str
    confidence: float
    match_method: str
    explanation: str
    raw_location_text: str
    alternative_section_id: Optional[UUID] = None
    alternative_section_code: Optional[str] = None

class DefectPreviewCriticalitySchema(BaseModel):
    predicted_score: int
    formula_baseline: float
    features: Dict[str, float]
    feature_contributions: Dict[str, float]
    dominant_factor: str
    justification: str

class DefectParsePreviewResponseSchema(BaseModel):
    status: str
    draft_defect: Dict[str, Any] = Field(..., description="Ready-to-submit payload for POST /departments/{dept}/defects")
    location_match: LocationMatchSchema
    preview_criticality: DefectPreviewCriticalitySchema
    extraction_metadata: Dict[str, Any]
    raw_text: str
    audio_transcription: Optional[Dict[str, Any]] = None
