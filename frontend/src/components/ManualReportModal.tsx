import React, { useState, useEffect } from 'react';
import { Department, BlockSection, Severity, WorkCategory, CrucialCascadeResult } from '../types';
import { createDepartmentDefect } from '../api/client';
import { X, PlusCircle, MapPin, Clock, CheckCircle2, AlertOctagon, AlertTriangle, ShieldAlert, Sparkles, ArrowRight } from 'lucide-react';

interface ManualReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  department: Department;
  sections: BlockSection[];
  onDefectCreated: () => void;
  onSwitchToCoaEmergency?: (incidentId?: string) => void;
}

export const ManualReportModal: React.FC<ManualReportModalProps> = ({
  isOpen,
  onClose,
  department,
  sections,
  onDefectCreated,
  onSwitchToCoaEmergency,
}) => {
  const [isEmergency, setIsEmergency] = useState<boolean>(false);
  const [selectedSectionId, setSelectedSectionId] = useState<string>(
    sections.length > 0 ? sections[0].id : ''
  );
  const [defectType, setDefectType] = useState('');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<Severity>('medium');
  const [workCategory, setWorkCategory] = useState<WorkCategory>('defect');
  const [duration, setDuration] = useState<number>(60);
  const [deadlineMinutes, setDeadlineMinutes] = useState<number>(90);
  const [requiresBlock, setRequiresBlock] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [systemTime, setSystemTime] = useState<string>(new Date().toLocaleString());
  const [cascadeResult, setCascadeResult] = useState<CrucialCascadeResult | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSystemTime(new Date().toLocaleString());
      setCascadeResult(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (sections.length > 0 && !selectedSectionId) {
      setSelectedSectionId(sections[0].id);
    }
  }, [sections, selectedSectionId]);

  if (!isOpen) return null;

  const handleToggleEmergency = (emergency: boolean) => {
    setIsEmergency(emergency);
    if (emergency) {
      setSeverity('critical');
      setRequiresBlock(true);
      setDuration(90);
      if (!defectType) {
        setDefectType(
          department === 'TMS'
            ? 'Severe Rail Fracture'
            : department === 'SMMS'
            ? 'Electronic Interlocking Failure'
            : '25kV Catenary Wire Snapped'
        );
      }
    } else {
      setSeverity('medium');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSectionId) return alert('Please select a corridor section.');
    if (!defectType.trim()) return alert('Please enter a defect type.');

    setSubmitting(true);
    try {
      const shortCode = Math.random().toString(36).substring(2, 7).toUpperCase();
      const code = `${department}-${isEmergency ? 'EMERG-' : ''}${shortCode}`;
      const deadlineDate = new Date(Date.now() + (deadlineMinutes || 90) * 60000).toISOString();

      const created = await createDepartmentDefect(department, {
        defect_code: code,
        block_section_id: selectedSectionId,
        defect_type: defectType.trim(),
        description: description.trim() || (isEmergency ? `Crucial Emergency Defect: ${defectType}` : 'Manual issue report'),
        severity: isEmergency ? 'critical' : severity,
        estimated_duration_min: duration,
        required_by: isEmergency ? deadlineDate : undefined,
        work_category: workCategory,
        input_source: isEmergency ? 'emergency' : 'manual',
        requires_block: requiresBlock,
        is_crucial_emergency: isEmergency,
      });

      if (created.emergency_cascade) {
        setCascadeResult(created.emergency_cascade);
      } else {
        onDefectCreated();
        onClose();
      }
    } catch (err: any) {
      alert(`Failed to report defect: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismissCascade = () => {
    setCascadeResult(null);
    onDefectCreated();
    onClose();
  };

  const selectedSection = sections.find((s) => s.id === selectedSectionId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className={`bg-slate-900 border rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden my-8 transition-all ${
        isEmergency ? 'border-rose-500/80 ring-2 ring-rose-500/30' : 'border-slate-700'
      }`}>
        {/* Header */}
        <div className={`p-4 sm:p-5 border-b flex items-center justify-between transition-colors ${
          isEmergency ? 'bg-rose-950/70 border-rose-800/80' : 'bg-slate-950 border-slate-800'
        }`}>
          <div className="flex items-center gap-2.5">
            <div className={`p-2 rounded-xl border ${
              isEmergency
                ? 'bg-rose-600/30 text-rose-400 border-rose-500/40 animate-pulse'
                : 'bg-blue-500/20 text-blue-400 border-blue-500/30'
            }`}>
              {isEmergency ? <AlertOctagon className="w-5 h-5 text-rose-400" /> : <PlusCircle className="w-5 h-5" />}
            </div>
            <div>
              <h3 className="font-bold text-white text-base flex items-center gap-2">
                <span>{isEmergency ? '🚨 Crucial Emergency Defect Intake' : `Report Maintenance Issue (${department})`}</span>
                {isEmergency && (
                  <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-rose-600 text-white rounded">
                    Department Imposed
                  </span>
                )}
              </h3>
              <p className="text-xs text-slate-400">
                {isEmergency
                  ? 'Triggers automated cascade: Free Gap ➔ Shadow Block ➔ Emergency Mode'
                  : 'Structured manual defect entry for department backlog'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode Selector Segmented Control */}
        <div className="p-3 bg-slate-950/80 border-b border-slate-800 flex gap-2 text-xs">
          <button
            type="button"
            onClick={() => handleToggleEmergency(false)}
            className={`flex-1 py-2 px-3 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              !isEmergency
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <CheckCircle2 className="w-4 h-4 text-blue-400" />
            <span>Standard Maintenance</span>
          </button>

          <button
            type="button"
            onClick={() => handleToggleEmergency(true)}
            className={`flex-1 py-2 px-3 rounded-lg font-bold transition flex items-center justify-center gap-1.5 ${
              isEmergency
                ? 'bg-rose-600 text-white border border-rose-400 shadow-lg shadow-rose-900/40'
                : 'text-rose-400 hover:text-rose-300 hover:bg-rose-950/30'
            }`}
          >
            <AlertTriangle className="w-4 h-4 text-amber-300" />
            <span>🚨 Crucial Emergency Defect</span>
          </button>
        </div>

        {/* Cascade Result Overlay */}
        {cascadeResult ? (
          <div className="p-6 flex flex-col gap-4 text-xs">
            <div className={`p-4 rounded-xl border flex flex-col gap-2.5 ${
              cascadeResult.cascade_step === 'emergency_invoked'
                ? 'bg-rose-950/80 border-rose-500 text-rose-100 shadow-lg shadow-rose-950'
                : cascadeResult.cascade_step === 'shadow_block_found'
                ? 'bg-teal-950/80 border-teal-500 text-teal-100'
                : 'bg-emerald-950/80 border-emerald-500 text-emerald-100'
            }`}>
              <div className="flex items-center gap-2">
                {cascadeResult.cascade_step === 'emergency_invoked' ? (
                  <AlertOctagon className="w-6 h-6 text-rose-400 animate-bounce" />
                ) : (
                  <Sparkles className="w-6 h-6 text-emerald-400" />
                )}
                <div>
                  <div className="font-extrabold text-sm uppercase tracking-wider">
                    {cascadeResult.cascade_step === 'emergency_invoked'
                      ? '🚨 Emergency Mode Automatically Invoked'
                      : cascadeResult.cascade_step === 'shadow_block_found'
                      ? '⚡ Shadow Block Opportunity Identified'
                      : '✅ Free Timetable Gap Identified'}
                  </div>
                  <div className="text-[11px] opacity-80">Automated Pipeline Verdict</div>
                </div>
              </div>

              <p className="text-xs leading-relaxed mt-1">
                {cascadeResult.message}
              </p>

              {cascadeResult.options && cascadeResult.options.length > 0 && (
                <div className="mt-2 pt-2 border-t border-rose-800/80 flex flex-col gap-1 text-[11px]">
                  <span className="font-bold text-amber-300">Generated Tactical Mitigation Options:</span>
                  {cascadeResult.options.map((opt, idx) => (
                    <div key={opt.option_id} className="bg-rose-900/50 p-2 rounded border border-rose-800/50 flex justify-between items-center">
                      <span className="font-semibold">{opt.label}</span>
                      <span className="text-rose-300">Impact: {opt.total_delay_minutes} min delay</span>
                    </div>
                  ))}
                  <span className="text-[10px] text-rose-300 italic mt-1">
                    Audible siren alarm and red priority banner activated at COA console.
                  </span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={handleDismissCascade}
                className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-white transition"
              >
                Close Notice
              </button>

              {cascadeResult.cascade_step === 'emergency_invoked' ? (
                <button
                  type="button"
                  onClick={() => {
                    if (onSwitchToCoaEmergency) {
                      onSwitchToCoaEmergency(cascadeResult.incident_id);
                    } else {
                      handleDismissCascade();
                    }
                  }}
                  className="px-5 py-2.5 rounded-xl font-black bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white shadow-lg flex items-center gap-2 border border-rose-400 animate-pulse cursor-pointer"
                >
                  <AlertOctagon className="w-4 h-4 text-white" />
                  <span>Review Tactical Operations in COA Cockpit</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleDismissCascade}
                  className="px-5 py-2.5 rounded-xl font-bold bg-blue-600 hover:bg-blue-500 text-white shadow-md flex items-center gap-2"
                >
                  <span>Acknowledge & Close</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ) : (
          /* Form Body */
          <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4 text-xs">
            {/* Live System Time Banner */}
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px]">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Clock className="w-3.5 h-3.5 text-blue-400" />
                Imposed System Time:
              </span>
              <span className="font-mono font-bold text-emerald-400">{systemTime}</span>
            </div>

            {/* Section Selector */}
            <div>
              <label className="block text-slate-300 font-semibold mb-1 flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-emerald-400" />
                Corridor Block Section:
              </label>
              <select
                value={selectedSectionId}
                onChange={(e) => setSelectedSectionId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-blue-500"
                required
              >
                {sections.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.section_code} ({s.from_station_code} ➔ {s.to_station_code}, {s.length_km} km)
                  </option>
                ))}
              </select>
            </div>

            {/* Defect Reason / Type */}
            <div>
              <label className="block text-slate-300 font-medium mb-1">
                {isEmergency ? 'Critical Defect Reason / Emergency Type:' : 'Defect Type / Title:'}
              </label>
              <input
                type="text"
                value={defectType}
                onChange={(e) => setDefectType(e.target.value)}
                placeholder={
                  isEmergency
                    ? 'e.g. Broken Rail at km 152/4, OHE Wire Snap, Electronic Interlocking Hang'
                    : 'e.g. Rail Joint Gap, Point Detection Failure, Catenary Dropper Broken'
                }
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>

            {/* Duration & Time Before It Must Be Solved (Deadline) */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  Time Required (Duration):
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={15}
                    max={480}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                    required
                  />
                  <span className="text-slate-400 font-medium">mins</span>
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-rose-400" />
                  Must Solve Within (Deadline):
                </label>
                <select
                  value={deadlineMinutes}
                  onChange={(e) => setDeadlineMinutes(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-rose-500"
                >
                  <option value={30}>Within 30 mins</option>
                  <option value={60}>Within 60 mins (1 hour)</option>
                  <option value={90}>Within 90 mins (1.5 hours)</option>
                  <option value={120}>Within 120 mins (2 hours)</option>
                  <option value={180}>Within 180 mins (3 hours)</option>
                  <option value={240}>Within 240 mins (4 hours)</option>
                </select>
              </div>
            </div>

            {/* Description / Field Notes */}
            <div>
              <label className="block text-slate-300 font-medium mb-1">
                {isEmergency ? 'Emergency Field Situation & Technical Observations:' : 'Detailed Technical Notes:'}
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder={
                  isEmergency
                    ? 'State immediate hazard, exact km marker, adjacent track clearance, and required emergency isolation equipment...'
                    : 'Provide exact kilometer marker, track condition, or replacement components required...'
                }
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Footer Actions */}
            <div className="pt-3 border-t border-slate-800 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className={`px-5 py-2.5 rounded-xl text-xs font-bold text-white transition shadow-lg flex items-center gap-2 ${
                  isEmergency
                    ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-900/40 animate-pulse'
                    : 'bg-blue-600 hover:bg-blue-500 shadow-blue-900/30'
                }`}
              >
                {isEmergency ? <AlertOctagon className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                <span>{submitting ? 'Running Cascade...' : isEmergency ? 'Impose Emergency Defect' : 'Submit Issue to Queue'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

