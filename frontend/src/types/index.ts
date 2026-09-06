export type Department = 'TMS' | 'SMMS' | 'TDMS';
export type ActiveView = 'COA' | Department;

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type DefectStatus = 'open' | 'requested' | 'allocated' | 'resolved';

export type WorkCategory = 'defect' | 'scheduled_maintenance' | 'overdue_task';

export type InputSource = 'manual' | 'nl_intake' | 'voice' | 'emergency';

export interface Defect {
  id: string;
  department: Department;
  defect_code: string;
  block_section_id: string;
  section_code?: string;
  from_station_code?: string;
  to_station_code?: string;
  defect_type: string;
  description?: string;
  severity: Severity;
  criticality_score: number;
  detected_at: string;
  required_by?: string;
  estimated_duration_min: number;
  requires_block: boolean;
  status: DefectStatus;
  created_at?: string;
  work_category: WorkCategory;
  input_source: InputSource;
  raw_report_text?: string;
}

export interface DefectCreatePayload {
  defect_code?: string;
  block_section_id: string;
  defect_type: string;
  description?: string;
  severity: Severity;
  criticality_score?: number;
  required_by?: string;
  estimated_duration_min: number;
  work_category: WorkCategory;
  input_source: InputSource;
  raw_report_text?: string;
  requires_block: boolean;
}

export interface BlockSection {
  id: string;
  section_code: string;
  from_station_id: string;
  to_station_id: string;
  from_station_code?: string;
  from_station_name?: string;
  to_station_code?: string;
  to_station_name?: string;
  track_code?: string;
  length_km?: number;
  sequence_order: number;
}

export interface DepartmentNotification {
  id?: string;
  type: 'approved' | 'declined' | 'deferred' | 'emergency' | 'info';
  title: string;
  message: string;
  timestamp: string;
  section_code?: string;
  department?: string;
  decision?: string;
}

export interface LocationMatch {
  block_section_id: string;
  section_code: string;
  from_station_code: string;
  to_station_code: string;
  track_code: string;
  direction: string;
  confidence: number;
  match_method: string;
  explanation: string;
  raw_location_text: string;
  alternative_section_id?: string;
  alternative_section_code?: string;
}

export interface MLScorePreview {
  predicted_score: number;
  formula_baseline: number;
  features: Record<string, number>;
  feature_contributions: Record<string, number>;
  dominant_factor: string;
  justification: string;
}

export interface DefectDraft {
  department: Department;
  block_section_id: string;
  section_code: string;
  defect_type: string;
  description: string;
  severity: Severity;
  criticality_score: number;
  required_by: string;
  estimated_duration_min: number;
  work_category: WorkCategory;
  input_source: InputSource;
  raw_report_text: string;
  requires_block: boolean;
  requires_track_block?: boolean;
  requires_signal_block?: boolean;
  requires_power_block?: boolean;
}

export interface DefectParsePreviewResponse {
  status: string;
  draft_defect: DefectDraft;
  location_match: LocationMatch;
  preview_criticality: MLScorePreview;
  extraction_metadata: {
    extraction_method?: string;
    urgency_hours?: number;
    raw_location_text?: string;
  };
  raw_text: string;
  audio_transcription?: {
    transcription: string;
    detected_language: string;
    audio_filename: string;
    transcription_model: string;
    transcription_status: string;
  };
}

// --- COA Master Interface Types ---

export interface Station {
  id: string;
  station_code: string;
  station_name: string;
  sequence_on_corridor: number;
  distance_from_origin_km?: number;
  latitude?: number;
  longitude?: number;
}

export interface TrainMovement {
  id: string;
  train_id: string;
  train_number: string;
  train_name?: string;
  train_type?: string;
  block_section_id: string;
  section_code: string;
  sequence_order: number;
  service_date: string;
  scheduled_entry: string;
  scheduled_exit: string;
  forecast_entry: string;
  forecast_exit: string;
  delay_minutes: number;
  status: string;
}

export interface CorridorBlock {
  id: string;
  block_request_id: string;
  block_section_id: string;
  section_code: string;
  from_station_code?: string;
  to_station_code?: string;
  planned_start: string;
  planned_end: string;
  duration_min: number;
  status: string;
  block_type: 'primary' | 'shadow';
  parent_block_id?: string;
  source_system?: string;
  defect_code?: string;
  defect_type?: string;
  criticality_score?: number;
  is_emergency?: boolean;
  optimization_run_at?: string;
  created_at?: string;
}

export interface ShadowCandidate {
  candidate_type?: string;
  candidate_id?: string;
  block_request_id?: string | null;
  defect_id?: string;
  source_system?: string;
  department?: string;
  defect_code: string;
  defect_type: string;
  criticality_score: number;
  estimated_duration_min: number;
  required_by?: string;
  detected_at?: string;
  duration_fit_ratio: number;
  margin_before_deadline_hours?: number;
  recommendation_reason: string;
}

export interface ShadowOpportunity {
  primary_block_id: string;
  block_section_id: string;
  section_code: string;
  from_station_code?: string;
  to_station_code?: string;
  primary_start: string;
  primary_end: string;
  primary_duration_min: number;
  primary_source_system?: string;
  primary_defect_code?: string;
  candidate_count: number;
  candidates: ShadowCandidate[];
}

export interface EmergencyOptionCard {
  option_id: string;
  label: string;
  planned_start: string;
  planned_end: string;
  duration_min: number;
  trains_affected_count: number;
  affected_train_numbers: string[];
  total_delay_minutes: number;
  is_shadow: boolean;
  parent_block_id?: string;
  resource_impact: string;
  sustainable: boolean;
  description: string;
}

export interface EmergencyIncident {
  id: string;
  source_system: string;
  block_section_id: string;
  section_code?: string;
  reported_text: string;
  status: 'reported' | 'action_recommended' | 'confirmed' | 'repairing' | 'safety_confirmed' | 'released';
  recommended_action?: 'hold' | 'divert' | 'block' | 'notify';
  recommendation_reason?: string;
  controller_decision?: string;
  block_request_id?: string;
  confirmed_at?: string;
  created_at: string;
}

export interface EmergencyAnalysisResponse {
  status: string;
  incident_id: string;
  source_system: string;
  section_code: string;
  incident_status: string;
  recommended_action: string;
  recommendation_reason: string;
  options: EmergencyOptionCard[];
}

export interface OptimizerResult {
  status: string;
  message: string;
  horizon_start: string;
  horizon_end: string;
  total_requests_considered: number;
  allocated_count: number;
  pending_count: number;
  new_allocations: any[];
}

export interface ReOptimizeResult {
  status: string;
  train_number: string;
  service_date: string;
  station_code: string;
  delay_minutes: number;
  criticality_threshold: number;
  conflicts_detected: number;
  trains_diverted_count: number;
  blocks_revoked_count: number;
  conflict_resolutions: any[];
  rescheduled_blocks: any[];
}

