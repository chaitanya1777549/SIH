import React, { useState } from 'react';
import { Department, BlockSection, Severity, WorkCategory } from '../types';
import { createDepartmentDefect } from '../api/client';
import { X, PlusCircle, MapPin, Clock, CheckCircle2 } from 'lucide-react';

interface ManualReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  department: Department;
  sections: BlockSection[];
  onDefectCreated: () => void;
}

export const ManualReportModal: React.FC<ManualReportModalProps> = ({
  isOpen,
  onClose,
  department,
  sections,
  onDefectCreated,
}) => {
  const [selectedSectionId, setSelectedSectionId] = useState<string>(
    sections.length > 0 ? sections[0].id : ''
  );
  const [defectType, setDefectType] = useState('');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<Severity>('medium');
  const [workCategory, setWorkCategory] = useState<WorkCategory>('defect');
  const [duration, setDuration] = useState<number>(60);
  const [requiresBlock, setRequiresBlock] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSectionId) return alert('Please select a corridor section.');
    if (!defectType.trim()) return alert('Please enter a defect type.');

    setSubmitting(true);
    try {
      const shortCode = Math.random().toString(36).substring(2, 7).toUpperCase();
      const code = `${department}-${shortCode}`;

      await createDepartmentDefect(department, {
        defect_code: code,
        block_section_id: selectedSectionId,
        defect_type: defectType.trim(),
        description: description.trim() || 'Manual issue report',
        severity,
        estimated_duration_min: duration,
        work_category: workCategory,
        input_source: 'manual',
        requires_block: requiresBlock,
      });

      onDefectCreated();
      onClose();
    } catch (err: any) {
      alert(`Failed to create defect: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden my-8">
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="bg-blue-500/20 text-blue-400 p-2 rounded-xl border border-blue-500/30">
              <PlusCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">
                Report New Maintenance Issue ({department})
              </h3>
              <p className="text-xs text-slate-400">Structured manual defect entry</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4 text-xs">
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

          {/* Defect Type */}
          <div>
            <label className="block text-slate-300 font-medium mb-1">Defect Type / Title:</label>
            <input
              type="text"
              value={defectType}
              onChange={(e) => setDefectType(e.target.value)}
              placeholder="e.g. Rail Joint Gap, Point Detection Failure, Catenary Dropper Broken"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
              required
            />
          </div>

          {/* Severity & Work Category */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Severity:</label>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
              >
                <option value="critical">Critical (Immediate Block)</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low (Routine Cycle)</option>
              </select>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Work Category:</label>
              <select
                value={workCategory}
                onChange={(e) => setWorkCategory(e.target.value as WorkCategory)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
              >
                <option value="defect">Defect Repair</option>
                <option value="scheduled_maintenance">Scheduled Maintenance</option>
                <option value="overdue_task">Overdue Task</option>
              </select>
            </div>
          </div>

          {/* Duration & Requires Block */}
          <div className="grid grid-cols-2 gap-3 items-center">
            <div>
              <label className="block text-slate-300 font-medium mb-1 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                Duration (minutes):
              </label>
              <input
                type="number"
                min={15}
                max={480}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>

            <div className="pt-4">
              <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={requiresBlock}
                  onChange={(e) => setRequiresBlock(e.target.checked)}
                  className="rounded bg-slate-950 border-slate-700 text-blue-600 focus:ring-0 w-4 h-4 cursor-pointer"
                />
                <span>Requires Track / Line Block</span>
              </label>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-slate-300 font-medium mb-1">Detailed Technical Notes:</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Provide exact kilometer marker, track condition, or replacement components required..."
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
              className="px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition shadow-lg shadow-blue-900/30 flex items-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{submitting ? 'Saving...' : 'Submit Issue to Queue'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
