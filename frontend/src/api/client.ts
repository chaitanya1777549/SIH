import {
  Department,
  Defect,
  DefectCreatePayload,
  BlockSection,
  DepartmentNotification,
  DefectParsePreviewResponse,
  MLScorePreview,
  Station,
  TrainMovement,
  CorridorBlock,
  ShadowOpportunity,
  EmergencyIncident,
  EmergencyAnalysisResponse,
  OptimizerResult,
  ReOptimizeResult,
  CrucialCascadeResult,
  ActiveEmergencyAlert,
} from '../types';

const DEFAULT_PROD_API = 'https://sih26027-backend-zlbr.onrender.com';

const getApiBase = () => {
  // 1. Explicit VITE_API_BASE_URL environment variable takes highest priority
  const envUrl = (import.meta as any).env?.VITE_API_BASE_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/$/, '');
  }

  // 2. If running locally on localhost or 127.0.0.1, use Vite proxy ('')
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return '';
    }
  }

  // 3. Fallback for production cloud deployments (Vercel, etc.)
  return DEFAULT_PROD_API;
};

export const API_BASE = getApiBase();

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return { status: 'error' };
    return await res.json();
  } catch (err) {
    return { status: 'offline' };
  }
}

export async function getDepartmentDefects(dept: Department): Promise<Defect[]> {
  const res = await fetch(`${API_BASE}/departments/${dept}/defects`);
  if (!res.ok) {
    throw new Error(`Failed to load defects for ${dept}: ${res.statusText}`);
  }
  return await res.json();
}

function formatErrorMessage(errData: any, fallback: string): string {
  if (!errData) return fallback;
  const detail = errData.detail ?? errData.message ?? errData;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => {
        if (typeof d === 'string') return d;
        const loc = d.loc ? d.loc.filter((x: any) => x !== 'body').join('.') : '';
        return loc ? `${loc}: ${d.msg || JSON.stringify(d)}` : (d.msg || JSON.stringify(d));
      })
      .join(' | ');
  }
  if (typeof detail === 'object') {
    return JSON.stringify(detail);
  }
  return String(detail);
}

export async function createDepartmentDefect(
  dept: Department,
  payload: DefectCreatePayload
): Promise<Defect> {
  const res = await fetch(`${API_BASE}/departments/${dept}/defects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to create defect'));
  }
  return await res.json();
}

export async function getDepartmentNotifications(
  dept: Department
): Promise<DepartmentNotification[]> {
  try {
    const res = await fetch(`${API_BASE}/departments/${dept}/notifications`);
    if (!res.ok) {
      // Fallback empty if no notifications yet
      return [];
    }
    const data = await res.json();
    return data.notifications || data || [];
  } catch (err) {
    console.warn('Could not fetch notifications:', err);
    return [];
  }
}

export async function getCorridorSections(): Promise<BlockSection[]> {
  const res = await fetch(`${API_BASE}/coa/sections`);
  if (!res.ok) {
    throw new Error('Failed to load corridor block sections');
  }
  return await res.json();
}

export async function parseDefectText(
  text: string,
  department?: Department
): Promise<DefectParsePreviewResponse> {
  const res = await fetch(`${API_BASE}/departments/parse-defect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      department: department || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to parse text report');
  }
  return await res.json();
}

export async function uploadVoiceReport(
  audioBlob: Blob,
  filename: string = 'voice_report.webm',
  department?: Department
): Promise<DefectParsePreviewResponse> {
  const formData = new FormData();
  formData.append('file', audioBlob, filename);
  if (department) {
    formData.append('department', department);
  }

  const res = await fetch(`${API_BASE}/departments/voice-intake-and-parse`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Voice intake processing failed');
  }
  return await res.json();
}

export async function previewDefectScore(
  dept: Department,
  params: {
    block_section_id: string;
    severity: string;
    required_by?: string | null;
    requires_block?: boolean;
    work_category?: string;
  }
): Promise<MLScorePreview> {
  const res = await fetch(`${API_BASE}/departments/${dept}/defects/preview-score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      block_section_id: params.block_section_id,
      severity: params.severity,
      required_by: params.required_by || null,
      requires_block: params.requires_block ?? true,
      work_category: params.work_category || 'defect',
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Criticality recalculation failed');
  }

  const data = await res.json();
  const exp = data.explainability;
  return {
    predicted_score: exp.predicted_score,
    formula_baseline: exp.formula_score,
    features: exp.feature_values || {},
    feature_contributions: exp.feature_contributions || {},
    dominant_factor: exp.dominant_factor,
    justification: exp.explanation,
  };
}

// ============================================================================
// COA Master Interface APIs
// ============================================================================

export async function fetchCorridorStations(): Promise<Station[]> {
  const res = await fetch(`${API_BASE}/coa/stations`);
  if (!res.ok) throw new Error('Failed to load stations');
  return await res.json();
}

export async function fetchCorridorTrains(dateVal?: string): Promise<TrainMovement[]> {
  const url = dateVal ? `${API_BASE}/coa/trains?date=${encodeURIComponent(dateVal)}` : `${API_BASE}/coa/trains`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load train movements');
  return await res.json();
}

export async function fetchCorridorBlocks(
  dateVal?: string,
  startDate?: string,
  endDate?: string,
  status?: string
): Promise<CorridorBlock[]> {
  const params = new URLSearchParams();
  if (dateVal) params.append('date', dateVal);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  if (status) params.append('status', status);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/coa/blocks?${qs}` : `${API_BASE}/coa/blocks`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load corridor blocks');
  return await res.json();
}

export async function runOptimizer(
  startDate: string,
  endDate: string,
  safetyBufferMin: number = 10,
  maxSolveTimeSec: number = 30
): Promise<OptimizerResult> {
  const res = await fetch(`${API_BASE}/coa/optimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      start_date: startDate,
      end_date: endDate,
      safety_buffer_min: safetyBufferMin,
      max_solve_time_sec: maxSolveTimeSec,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Optimizer run failed'));
  }
  return await res.json();
}

export async function fetchShadowOpportunities(): Promise<ShadowOpportunity[]> {
  const res = await fetch(`${API_BASE}/coa/shadow-opportunities`);
  if (!res.ok) throw new Error('Failed to load shadow opportunities');
  return await res.json();
}

export async function attachShadowBlock(
  primaryBlockId: string,
  defectId?: string,
  department?: string,
  blockRequestId?: string | null
): Promise<any> {
  const res = await fetch(`${API_BASE}/coa/shadow-attach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      primary_block_id: primaryBlockId,
      defect_id: defectId || null,
      block_request_id: blockRequestId || null,
      department: department || null,
      source_system: department || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to attach shadow block'));
  }
  return await res.json();
}

export async function discardShadowOpportunity(
  primaryBlockId: string,
  defectId?: string,
  department?: string,
  blockRequestId?: string | null
): Promise<any> {
  const res = await fetch(`${API_BASE}/coa/shadow-discard`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      primary_block_id: primaryBlockId,
      defect_id: defectId || null,
      block_request_id: blockRequestId || null,
      department: department || null,
      source_system: department || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to discard shadow proposal'));
  }
  return await res.json();
}

export async function simulateDelayAndReoptimize(
  trainNumber: string,
  serviceDate: string,
  stationCode: string,
  delayMinutes: number,
  criticalityThreshold: number = 60
): Promise<ReOptimizeResult> {
  const res = await fetch(`${API_BASE}/coa/trains/delay-and-reoptimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      train_number: trainNumber,
      service_date: serviceDate,
      station_code: stationCode,
      delay_minutes: delayMinutes,
      criticality_threshold: criticalityThreshold,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Delay re-optimization failed'));
  }
  return await res.json();
}

export async function fetchEmergencyIncidents(status?: string): Promise<EmergencyIncident[]> {
  const url = status ? `${API_BASE}/coa/emergency/incidents?status=${encodeURIComponent(status)}` : `${API_BASE}/coa/emergency/incidents`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load emergency incidents');
  return await res.json();
}

export async function fetchEmergencyIncidentAnalysis(incidentId: string): Promise<EmergencyAnalysisResponse> {
  const res = await fetch(`${API_BASE}/coa/emergency/incidents/${incidentId}`);
  if (!res.ok) throw new Error('Failed to load incident analysis');
  return await res.json();
}

export async function reportEmergencyIncident(payload: {
  source_system: string;
  block_section_id: string;
  reported_text: string;
  defect_type?: string;
  severity?: string;
  estimated_duration_min?: number;
}): Promise<EmergencyAnalysisResponse> {
  const res = await fetch(`${API_BASE}/coa/emergency/incidents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to report emergency incident'));
  }
  return await res.json();
}

export async function confirmEmergencyDecision(
  incidentId: string,
  decision: string,
  selectedOptionId?: string,
  notes?: string
): Promise<any> {
  const res = await fetch(`${API_BASE}/coa/emergency/incidents/${incidentId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      decision,
      selected_option_id: selectedOptionId || null,
      notes: notes || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to confirm emergency decision'));
  }
  return await res.json();
}

export async function advanceEmergencyStatus(
  incidentId: string,
  targetStatus: string,
  notes?: string
): Promise<any> {
  const res = await fetch(`${API_BASE}/coa/emergency/incidents/${incidentId}/advance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_status: targetStatus,
      notes: notes || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to advance emergency lifecycle'));
  }
  return await res.json();
}

export async function evaluateCrucialDefect(payload: {
  source_system: string;
  block_section_id: string;
  reason: string;
  estimated_duration_min: number;
  required_by_minutes?: number;
  defect_type?: string;
  defect_id?: string;
}): Promise<CrucialCascadeResult> {
  const res = await fetch(`${API_BASE}/coa/emergency/evaluate-crucial`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatErrorMessage(err, 'Failed to evaluate crucial defect cascade'));
  }
  return await res.json();
}

export async function fetchActiveEmergencyAlert(): Promise<ActiveEmergencyAlert> {
  const res = await fetch(`${API_BASE}/coa/emergency/active-alert`);
  if (!res.ok) {
    throw new Error('Failed to load active emergency alert');
  }
  return await res.json();
}



