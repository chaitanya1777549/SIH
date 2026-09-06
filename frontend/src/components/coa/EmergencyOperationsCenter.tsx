import React, { useState, useEffect } from 'react';
import {
  EmergencyIncident,
  EmergencyAnalysisResponse,
  EmergencyOptionCard,
  BlockSection,
} from '../../types';
import {
  fetchEmergencyIncidents,
  fetchEmergencyIncidentAnalysis,
  reportEmergencyIncident,
  confirmEmergencyDecision,
  advanceEmergencyStatus,
} from '../../api/client';
import { startEmergencySiren, stopEmergencySiren, isSirenActive } from '../../utils/siren';
import {
  AlertOctagon,
  ShieldAlert,
  ShieldCheck,
  Clock,
  Train,
  CheckCircle2,
  ArrowRight,
  Plus,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  FileCheck,
  Sliders,
  Volume2,
  VolumeX,
} from 'lucide-react';

interface EmergencyOperationsCenterProps {
  sections: BlockSection[];
  onRefreshCorridor?: () => Promise<void>;
  targetIncidentId?: string | null;
  onDecisionConfirmed?: () => void;
}

export const EmergencyOperationsCenter: React.FC<EmergencyOperationsCenterProps> = ({
  sections,
  onRefreshCorridor,
  targetIncidentId,
  onDecisionConfirmed,
}) => {
  const [incidents, setIncidents] = useState<EmergencyIncident[]>([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(targetIncidentId || null);
  const [activeAnalysis, setActiveAnalysis] = useState<EmergencyAnalysisResponse | null>(null);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isReportingModalOpen, setIsReportingModalOpen] = useState<boolean>(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [sirenPlaying, setSirenPlaying] = useState<boolean>(isSirenActive());

  useEffect(() => {
    if (targetIncidentId) {
      setSelectedIncidentId(targetIncidentId);
    }
  }, [targetIncidentId]);

  const handleToggleSiren = () => {
    if (sirenPlaying) {
      stopEmergencySiren();
      setSirenPlaying(false);
    } else {
      startEmergencySiren();
      setSirenPlaying(true);
    }
  };

  // New Incident Form State
  const [formSource, setFormSource] = useState<'TMS' | 'SMMS' | 'TDMS'>('TMS');
  const [formSectionId, setFormSectionId] = useState<string>('');
  const [formReportedText, setFormReportedText] = useState<string>('');
  const [formDefectType, setFormDefectType] = useState<string>('Rail Fracture');
  const [formDuration, setFormDuration] = useState<number>(90);

  // Load Incidents
  const loadIncidents = async () => {
    try {
      setIsLoading(true);
      const data = await fetchEmergencyIncidents();
      setIncidents(data);
      
      // Select priority: targetIncidentId > active unconfirmed incident > existing > data[0]
      if (targetIncidentId && data.some((i) => i.id === targetIncidentId)) {
        setSelectedIncidentId(targetIncidentId);
      } else if (!selectedIncidentId || !data.some((i) => i.id === selectedIncidentId)) {
        const activeOne = data.find((i) => i.status === 'action_recommended' || i.status === 'reported');
        setSelectedIncidentId(activeOne ? activeOne.id : data.length > 0 ? data[0].id : null);
      }
    } catch (err: any) {
      console.error('Failed to load emergency incidents:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadIncidents();
    if (sections.length > 0 && !formSectionId) {
      setFormSectionId(sections[0].id);
    }
  }, [sections]);

  // Load Analysis when selected incident changes
  useEffect(() => {
    if (!selectedIncidentId) {
      setActiveAnalysis(null);
      return;
    }
    const loadAnalysis = async () => {
      try {
        const analysis = await fetchEmergencyIncidentAnalysis(selectedIncidentId);
        setActiveAnalysis(analysis);
        if (analysis.options && analysis.options.length > 0) {
          setSelectedOptionId(analysis.options[0].option_id);
        }
      } catch (err: any) {
        console.error('Failed to fetch incident analysis:', err);
      }
    };
    loadAnalysis();
  }, [selectedIncidentId]);

  // Submit New Incident
  const handleReportIncident = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionSuccess(null);
    setActionError(null);

    try {
      const res = await reportEmergencyIncident({
        source_system: formSource,
        block_section_id: formSectionId,
        reported_text: formReportedText || `Emergency ${formDefectType} reported on corridor`,
        defect_type: formDefectType,
        severity: 'critical',
        estimated_duration_min: formDuration,
      });

      setActionSuccess(`Emergency Incident registered! Section conflict analysis generated.`);
      setIsReportingModalOpen(false);
      setFormReportedText('');
      await loadIncidents();
      setSelectedIncidentId(res.incident_id);
      if (onRefreshCorridor) await onRefreshCorridor();
    } catch (err: any) {
      setActionError(err.message || 'Failed to report incident');
    }
  };

  // Confirm Controller Decision
  const handleConfirmDecision = async () => {
    if (!selectedIncidentId) return;
    setActionSuccess(null);
    setActionError(null);

    try {
      const res = await confirmEmergencyDecision(
        selectedIncidentId,
        'block',
        selectedOptionId || undefined,
        'Approved by COA Senior Controller via EOC Matrix'
      );
      // 1. Immediately silence the siren upon controller decision confirmation
      stopEmergencySiren();
      setSirenPlaying(false);

      // 2. Notify parent CoaDashboard to clear active alert banner and mute siren immediately
      if (onDecisionConfirmed) {
        onDecisionConfirmed();
      }

      setActionSuccess(res.message || 'Decision confirmed! Emergency possession created.');
      await loadIncidents();
      const updatedAnalysis = await fetchEmergencyIncidentAnalysis(selectedIncidentId);
      setActiveAnalysis(updatedAnalysis);
      if (onRefreshCorridor) await onRefreshCorridor();
    } catch (err: any) {
      setActionError(err.message || 'Failed to confirm decision');
    }
  };

  // Advance Repair / Safety Lifecycle
  const handleAdvanceLifecycle = async (targetStatus: string) => {
    if (!selectedIncidentId) return;
    setActionSuccess(null);
    setActionError(null);

    try {
      const res = await advanceEmergencyStatus(
        selectedIncidentId,
        targetStatus,
        `Controller advanced status to ${targetStatus}`
      );
      setActionSuccess(res.message || `Incident lifecycle advanced to ${targetStatus}`);
      await loadIncidents();
      const updatedAnalysis = await fetchEmergencyIncidentAnalysis(selectedIncidentId);
      setActiveAnalysis(updatedAnalysis);
      if (onRefreshCorridor) await onRefreshCorridor();
    } catch (err: any) {
      setActionError(err.message || 'Failed to advance status');
    }
  };

  const selectedIncident = incidents.find((i) => i.id === selectedIncidentId);

  const formatIsoTime = (isoString?: string) => {
    if (!isoString) return '--:--';
    try {
      const d = new Date(isoString);
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-5 text-white">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-rose-500/20 text-rose-400 rounded-lg animate-pulse">
            <AlertOctagon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold tracking-wide flex items-center gap-2">
              Emergency Operations Center (EOC)
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-rose-900/80 text-rose-200 font-bold border border-rose-700">
                {incidents.filter((i) => i.status !== 'released').length} Active Situations
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              High-urgency defect conflict analysis, 4-tier tactical options, and closed-loop corridor safety release
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {sirenPlaying && (
            <button
              onClick={handleToggleSiren}
              className="flex items-center gap-1.5 bg-rose-800/90 hover:bg-rose-700 text-amber-300 text-xs font-bold px-3 py-2 rounded-lg border border-rose-500 shadow-md transition animate-pulse"
              title="Silence Siren"
            >
              <VolumeX className="w-4 h-4 text-amber-300" />
              <span>Silence Siren</span>
            </button>
          )}
          <button
            onClick={() => setIsReportingModalOpen(true)}
            className="flex items-center gap-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold px-3.5 py-2 rounded-lg shadow-md transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Report Emergency Incident
          </button>
          <button
            onClick={() => loadIncidents()}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold px-3 py-2 rounded-lg border border-slate-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {actionSuccess && (
        <div className="p-3 bg-emerald-950/80 border border-emerald-600/70 rounded-lg text-xs text-emerald-300 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 flex-shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="p-3 bg-rose-950/80 border border-rose-600/70 rounded-lg text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Main Grid: Incident Selector (Left) & Tactical Analysis (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Incident List Column (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span>Incident Queue ({incidents.length})</span>
          </div>

          <div className="flex flex-col gap-2 max-h-[580px] overflow-y-auto pr-1">
            {incidents.length === 0 ? (
              <div className="p-6 text-center border border-slate-800 border-dashed rounded-lg bg-slate-950/40 text-xs text-slate-500">
                No emergency incidents logged. Corridor operating normally.
              </div>
            ) : (
              incidents.map((inc) => {
                const isSelected = inc.id === selectedIncidentId;
                const isReleased = inc.status === 'released';
                const isConfirmed = inc.status === 'confirmed' || inc.status === 'repairing' || inc.status === 'safety_confirmed';

                return (
                  <button
                    key={inc.id}
                    onClick={() => setSelectedIncidentId(inc.id)}
                    className={`text-left p-3 rounded-lg border transition-all flex flex-col gap-1.5 ${
                      isSelected
                        ? 'bg-slate-800 border-rose-500 shadow-md ring-1 ring-rose-500/40'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-slate-200">
                        {inc.section_code || 'SECTION'}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase ${
                          isReleased
                            ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700/60'
                            : isConfirmed
                            ? 'bg-amber-900/60 text-amber-300 border border-amber-700/60'
                            : 'bg-rose-900/60 text-rose-300 border border-rose-700/60'
                        }`}
                      >
                        {inc.status.replace('_', ' ')}
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-300 line-clamp-2">
                      {inc.reported_text}
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/80">
                      <span>Dept: {inc.source_system}</span>
                      <span>{new Date(inc.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Incident Tactical Analysis Panel (8 cols) */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          {!selectedIncident ? (
            <div className="h-full flex items-center justify-center p-12 border border-slate-800 rounded-lg text-slate-500 text-xs">
              Select an emergency incident from the left to inspect tactical options.
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* Incident Header Details */}
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-xs font-black bg-rose-600 text-white">
                      EMERGENCY
                    </span>
                    <span className="font-bold text-sm text-slate-100">
                      {selectedIncident.section_code}
                    </span>
                    <span className="text-xs text-slate-400">
                      Source: {selectedIncident.source_system}
                    </span>
                  </div>

                  <div className="text-xs text-slate-400">
                    Logged: {new Date(selectedIncident.created_at).toLocaleString()}
                  </div>
                </div>

                <div className="text-xs text-slate-200 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                  <span className="font-semibold text-rose-300">Reported Issue: </span>
                  {selectedIncident.reported_text}
                </div>

                {/* Algorithmic Triage Cascade Verification */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-2.5">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-rose-300">
                      <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                      Automated 3-Stage Cascade Verification
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Department Origin: {selectedIncident.source_system} Field Defect
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                    <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-300 text-[11px]">1. Timetable Free Gap</span>
                        <span className="text-[10px] font-bold text-rose-400 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800">
                          ❌ UNAVAILABLE
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-tight">
                        No natural 60-90m train-free slot exists before required deadline. Standard block impossible without regulation.
                      </p>
                    </div>

                    <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-300 text-[11px]">2. Shadow Piggyback</span>
                        <span className="text-[10px] font-bold text-rose-400 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800">
                          ❌ NO OVERLAP
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-tight">
                        No active primary possession approved on {selectedIncident.section_code || 'section'} before resolution deadline.
                      </p>
                    </div>

                    <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-600/60 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-rose-300 text-[11px]">3. Emergency Escalation</span>
                        <span className="text-[10px] font-black text-rose-200 bg-rose-700 px-1.5 py-0.5 rounded border border-rose-500 animate-pulse">
                          🚨 AUTO-TRIGGERED
                        </span>
                      </div>
                      <p className="text-[10px] text-rose-200/90 leading-tight">
                        Direct COA Siren alert sounded. Multi-option tactical mitigation matrix calculated below for controller approval.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Tactical Heuristic Recommendation */}
                {activeAnalysis && (
                  <div className="flex items-start gap-3 p-3 bg-indigo-950/40 border border-indigo-500/40 rounded-lg">
                    <Sparkles className="w-4 h-4 text-indigo-400 mt-0.5 flex-shrink-0" />
                    <div className="flex flex-col gap-0.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">Heuristic Engine Recommendation:</span>
                        <span className="font-black text-indigo-300 uppercase px-2 py-0.2 rounded bg-indigo-900/60 border border-indigo-700">
                          {activeAnalysis.recommended_action}
                        </span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed mt-1">
                        {activeAnalysis.recommendation_reason}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* CANDIDATE OPTION CARDS (Before Confirmation) */}
              {selectedIncident.status === 'reported' || selectedIncident.status === 'action_recommended' ? (
                <div className="flex flex-col gap-3">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-amber-400" />
                    Tactical Block Decision Matrix (Multi-Option Comparison)
                  </div>

                  {activeAnalysis && activeAnalysis.options && activeAnalysis.options.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {activeAnalysis.options.map((opt) => {
                        const isSelected = selectedOptionId === opt.option_id;

                        return (
                          <div
                            key={opt.option_id}
                            onClick={() => setSelectedOptionId(opt.option_id)}
                            className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col justify-between gap-3 ${
                              isSelected
                                ? 'bg-slate-800/90 border-amber-500 shadow-xl ring-1 ring-amber-500/40'
                                : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                            }`}
                          >
                            <div className="flex flex-col gap-2">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-xs text-amber-400">
                                  {opt.label}
                                </span>
                                {opt.sustainable ? (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
                                    SUSTAINABLE
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700 animate-pulse">
                                    EXCEEDS SAFETY LIMIT
                                  </span>
                                )}
                              </div>

                              <div className="text-xs font-medium text-slate-300">
                                {opt.description}
                              </div>

                              <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                                <div>
                                  <span className="text-slate-400">Possession Window:</span>
                                  <div className="font-semibold text-slate-200">
                                    {formatIsoTime(opt.planned_start)} – {formatIsoTime(opt.planned_end)}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">Duration:</span>
                                  <div className="font-semibold text-slate-200">
                                    {opt.duration_min} min
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">Trains Affected:</span>
                                  <div className="font-semibold text-rose-400">
                                    {opt.trains_affected_count} train(s)
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">Total Delay Impact:</span>
                                  <div className="font-semibold text-rose-400">
                                    {opt.total_delay_minutes} min
                                  </div>
                                </div>
                              </div>

                              {opt.affected_train_numbers.length > 0 && (
                                <div className="text-[10px] text-slate-400">
                                  Regulated: #{opt.affected_train_numbers.join(', #')}
                                </div>
                              )}
                            </div>

                            <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                              <span className="text-[11px] font-semibold text-slate-400">
                                {opt.resource_impact}
                              </span>
                              <input
                                type="radio"
                                name="emergency_option"
                                checked={isSelected}
                                onChange={() => setSelectedOptionId(opt.option_id)}
                                className="w-4 h-4 text-amber-500 focus:ring-amber-400"
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="p-4 text-center border border-slate-800 rounded-lg text-slate-500 text-xs">
                      Computing tactical options...
                    </div>
                  )}

                  {/* Confirm Button */}
                  <div className="flex items-center justify-end pt-2">
                    <button
                      onClick={handleConfirmDecision}
                      disabled={!selectedOptionId}
                      className="flex items-center gap-2 bg-gradient-to-r from-amber-600 to-rose-600 hover:from-amber-500 hover:to-rose-500 disabled:opacity-50 text-white text-xs font-bold px-6 py-2.5 rounded-lg shadow-lg transition"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      Authorize Controller Directive & Allocate Block
                    </button>
                  </div>
                </div>
              ) : (
                /* REPAIR & SAFETY RELEASE LIFECYCLE (After Confirmation) */
                <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 flex flex-col gap-4">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <FileCheck className="w-4 h-4 text-emerald-400" />
                    Operational Repair & Corridor Reopening Lifecycle
                  </div>

                  {/* Stepper */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div
                      className={`p-3 rounded-lg border text-xs flex flex-col gap-1 ${
                        selectedIncident.status === 'confirmed'
                          ? 'bg-amber-950/60 border-amber-500 text-amber-200'
                          : 'bg-slate-900 border-slate-800 text-slate-400'
                      }`}
                    >
                      <span className="font-bold text-[10px]">STEP 1</span>
                      <span className="font-semibold">Block Confirmed</span>
                      <span className="text-[10px]">Possession ready</span>
                    </div>

                    <div
                      className={`p-3 rounded-lg border text-xs flex flex-col gap-1 ${
                        selectedIncident.status === 'repairing'
                          ? 'bg-amber-950/60 border-amber-500 text-amber-200'
                          : 'bg-slate-900 border-slate-800 text-slate-400'
                      }`}
                    >
                      <span className="font-bold text-[10px]">STEP 2</span>
                      <span className="font-semibold">Repair Active</span>
                      <span className="text-[10px]">Ground team working</span>
                    </div>

                    <div
                      className={`p-3 rounded-lg border text-xs flex flex-col gap-1 ${
                        selectedIncident.status === 'safety_confirmed'
                          ? 'bg-sky-950/60 border-sky-500 text-sky-200'
                          : 'bg-slate-900 border-slate-800 text-slate-400'
                      }`}
                    >
                      <span className="font-bold text-[10px]">STEP 3</span>
                      <span className="font-semibold">Safety Certified</span>
                      <span className="text-[10px]">Track tested safe</span>
                    </div>

                    <div
                      className={`p-3 rounded-lg border text-xs flex flex-col gap-1 ${
                        selectedIncident.status === 'released'
                          ? 'bg-emerald-950/60 border-emerald-500 text-emerald-200'
                          : 'bg-slate-900 border-slate-800 text-slate-400'
                      }`}
                    >
                      <span className="font-bold text-[10px]">STEP 4</span>
                      <span className="font-semibold">Released & Open</span>
                      <span className="text-[10px]">Commercial traffic resumed</span>
                    </div>
                  </div>

                  {/* Lifecycle Progression Buttons */}
                  <div className="flex flex-wrap items-center justify-end gap-3 pt-3 border-t border-slate-800">
                    {selectedIncident.status === 'confirmed' && (
                      <button
                        onClick={() => handleAdvanceLifecycle('repairing')}
                        className="flex items-center gap-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold px-4 py-2 rounded-lg shadow transition"
                      >
                        <ArrowRight className="w-3.5 h-3.5" />
                        Ground Crew On Site: Mark In Repair
                      </button>
                    )}

                    {selectedIncident.status === 'repairing' && (
                      <button
                        onClick={() => handleAdvanceLifecycle('safety_confirmed')}
                        className="flex items-center gap-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold px-4 py-2 rounded-lg shadow transition"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        Sign-off Safety Inspection: Confirm Track Safety
                      </button>
                    )}

                    {selectedIncident.status === 'safety_confirmed' && (
                      <button
                        onClick={() => handleAdvanceLifecycle('released')}
                        className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-2 rounded-lg shadow transition"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Formal Release: Reopen Corridor to Traffic
                      </button>
                    )}

                    {selectedIncident.status === 'released' && (
                      <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                        <CheckCircle2 className="w-4 h-4" />
                        Incident Closed. Corridor fully released.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Report Incident Modal */}
      {isReportingModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 shadow-2xl flex flex-col gap-4 text-white">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-base flex items-center gap-2 text-rose-400">
                <AlertOctagon className="w-5 h-5" />
                Report Urgent Corridor Incident
              </h3>
              <button
                onClick={() => setIsReportingModalOpen(false)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleReportIncident} className="flex flex-col gap-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-slate-300 font-medium">Reporting Department</label>
                  <select
                    value={formSource}
                    onChange={(e) => setFormSource(e.target.value as any)}
                    className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-rose-500"
                  >
                    <option value="TMS">TMS (Track Engineering)</option>
                    <option value="SMMS">SMMS (Signal & Telecom)</option>
                    <option value="TDMS">TDMS (Traction / OHE)</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-slate-300 font-medium">Corridor Section</label>
                  <select
                    value={formSectionId}
                    onChange={(e) => setFormSectionId(e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-rose-500"
                  >
                    {sections.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.section_code} ({s.from_station_code} → {s.to_station_code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-slate-300 font-medium">Defect Type</label>
                  <input
                    type="text"
                    value={formDefectType}
                    onChange={(e) => setFormDefectType(e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-rose-500"
                    placeholder="e.g. Rail Fracture"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-slate-300 font-medium">Estimated Duration (min)</label>
                  <input
                    type="number"
                    min={15}
                    max={360}
                    value={formDuration}
                    onChange={(e) => setFormDuration(Number(e.target.value))}
                    className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-rose-500"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-slate-300 font-medium">Incident Description / Observations</label>
                <textarea
                  rows={3}
                  value={formReportedText}
                  onChange={(e) => setFormReportedText(e.target.value)}
                  placeholder="Describe track condition, bridge / point number, or hazard details..."
                  className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-rose-500"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsReportingModalOpen(false)}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold px-4 py-2 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="bg-rose-600 hover:bg-rose-500 text-white font-bold px-4 py-2 rounded-lg shadow-md transition"
                >
                  Submit & Run Conflict Matrix
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
