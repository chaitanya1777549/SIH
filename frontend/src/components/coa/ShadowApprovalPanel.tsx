import React, { useState, useMemo } from 'react';
import { ShadowOpportunity, ShadowCandidate } from '../../types';
import { attachShadowBlock, discardShadowOpportunity } from '../../api/client';
import { Sparkles, Check, X, ShieldCheck, Clock, RefreshCw, AlertCircle, Calendar, Info } from 'lucide-react';

interface ShadowApprovalPanelProps {
  opportunities: ShadowOpportunity[];
  onRefresh: () => Promise<void>;
}

export const ShadowApprovalPanel: React.FC<ShadowApprovalPanelProps> = ({
  opportunities,
  onRefresh,
}) => {
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Filters
  const [synergyFilter, setSynergyFilter] = useState<'ALL' | 'CROSS' | 'INTRA'>('ALL');
  const [deptFilter, setDeptFilter] = useState<string>('ALL');

  const formatIsoTime = (isoString?: string) => {
    if (!isoString) return '--:--';
    try {
      const d = new Date(isoString);
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return isoString;
    }
  };

  const formatIsoDate = (isoString?: string) => {
    if (!isoString) return '--';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
      return '';
    }
  };

  const formatShortDate = (isoString?: string) => {
    if (!isoString) return '--';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', { day: '2-digit', month: 'short' });
    } catch {
      return '';
    }
  };

  const formatIsoDateTime = (isoString?: string) => {
    if (!isoString) return null;
    try {
      const d = new Date(isoString);
      const datePart = d.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
      const timePart = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      return `${datePart} ${timePart}`;
    } catch {
      return isoString;
    }
  };

  const calculateShadowEndTime = (startIso?: string, durationMin?: number) => {
    if (!startIso || !durationMin) return '--:--';
    try {
      const d = new Date(startIso);
      const end = new Date(d.getTime() + durationMin * 60000);
      return `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`;
    } catch {
      return '--:--';
    }
  };

  // Count how many primary blocks each defect code appears under
  const defectOpportunityCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const opp of opportunities) {
      for (const cand of opp.candidates) {
        counts.set(cand.defect_code, (counts.get(cand.defect_code) || 0) + 1);
      }
    }
    return counts;
  }, [opportunities]);

  // Filtered Opportunities based on user selection
  const filteredOpportunities = useMemo(() => {
    return opportunities
      .map((opp) => {
        const matchingCandidates = opp.candidates.filter((cand) => {
          const candDept = cand.department || cand.source_system || 'TMS';
          const isCross = candDept !== (opp.primary_source_system || 'TMS');
          if (synergyFilter === 'CROSS' && !isCross) return false;
          if (synergyFilter === 'INTRA' && isCross) return false;
          if (deptFilter !== 'ALL' && candDept !== deptFilter) return false;
          return true;
        });
        return {
          ...opp,
          candidates: matchingCandidates,
        };
      })
      .filter((opp) => opp.candidates.length > 0);
  }, [opportunities, synergyFilter, deptFilter]);

  const handleApprove = async (opp: ShadowOpportunity, cand: ShadowCandidate) => {
    const itemKey = cand.candidate_id || cand.defect_id || cand.block_request_id || cand.defect_code;
    const key = `${opp.primary_block_id}-${itemKey}`;
    setProcessingId(key);
    setActionSuccess(null);
    setActionError(null);

    const dept = cand.department || cand.source_system || 'TMS';
    try {
      await attachShadowBlock(opp.primary_block_id, cand.defect_id, dept, cand.block_request_id);
      setActionSuccess(
        `Approved! Successfully attached ${dept} shadow block (${cand.defect_code}) on section ${opp.section_code} for ${formatIsoDate(opp.primary_start)} (${formatIsoTime(opp.primary_start)} – ${calculateShadowEndTime(opp.primary_start, cand.estimated_duration_min)}). Notification dispatched!`
      );
      await onRefresh();
    } catch (err: any) {
      setActionError(err.message || 'Failed to attach shadow block');
    } finally {
      setProcessingId(null);
    }
  };

  const handleDiscard = async (opp: ShadowOpportunity, cand: ShadowCandidate) => {
    const itemKey = cand.candidate_id || cand.defect_id || cand.block_request_id || cand.defect_code;
    const key = `${opp.primary_block_id}-${itemKey}`;
    setProcessingId(key);
    setActionSuccess(null);
    setActionError(null);

    const dept = cand.department || cand.source_system || 'TMS';
    try {
      await discardShadowOpportunity(opp.primary_block_id, cand.defect_id, dept, cand.block_request_id);
      setActionSuccess(
        `Discarded shadow proposal for ${cand.defect_code}. Department notified.`
      );
      await onRefresh();
    } catch (err: any) {
      setActionError(err.message || 'Failed to discard proposal');
    } finally {
      setProcessingId(null);
    }
  };

  const totalCandidates = opportunities.reduce((acc, o) => acc + o.candidates.length, 0);

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm flex flex-col gap-5 text-slate-800">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-50 text-purple-700 rounded-xl border border-purple-100">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-extrabold tracking-tight text-slate-900 flex items-center gap-2">
              1-Click Shadow Block Piggyback Center
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 font-bold border border-purple-200">
                {totalCandidates} Active Opportunities
              </span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Multi-department co-possession engine. Schedule secondary maintenance concurrently inside existing primary possession windows with zero additional train delay.
            </p>
          </div>
        </div>

        <button
          onClick={() => onRefresh()}
          className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold px-3.5 py-2 rounded-xl border border-slate-300 shadow-xs transition"
        >
          <RefreshCw className="w-3.5 h-3.5 text-purple-600" />
          <span>Scan Opportunities</span>
        </button>
      </div>

      {/* Explanatory Context Banner */}
      <div className="bg-gradient-to-r from-purple-50/70 via-indigo-50/50 to-blue-50/70 border border-purple-200/80 rounded-2xl p-4 text-xs text-slate-700 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-purple-600 text-white rounded-xl shadow-xs mt-0.5">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <span className="font-extrabold text-slate-900 text-xs block">
              How Shadow Piggybacking Works on Corridors
            </span>
            <span className="text-slate-600 text-[11px] leading-relaxed">
              When a department logs a defect requiring a block, the system automatically checks if <strong>any scheduled primary possession</strong> on that same track section has room. If multiple primary blocks exist across September, each one is presented as an alternative date/time slot.
            </span>
          </div>
        </div>

        {/* Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center bg-white rounded-xl p-1 border border-slate-200 shadow-2xs text-xs">
            <button
              onClick={() => setSynergyFilter('ALL')}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                synergyFilter === 'ALL'
                  ? 'bg-purple-600 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All Slots
            </button>
            <button
              onClick={() => setSynergyFilter('CROSS')}
              className={`px-2.5 py-1 rounded-lg font-bold transition flex items-center gap-1 ${
                synergyFilter === 'CROSS'
                  ? 'bg-purple-600 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
              title="Only show candidates from different departments than the primary block holder"
            >
              <span>Cross-Dept Only</span>
            </button>
            <button
              onClick={() => setSynergyFilter('INTRA')}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                synergyFilter === 'INTRA'
                  ? 'bg-purple-600 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Intra-Dept
            </button>
          </div>

          <select
            value={deptFilter}
            onChange={(e) => setDeptFilter(e.target.value)}
            className="bg-white border border-slate-200 text-slate-700 text-xs rounded-xl px-2.5 py-1.5 font-bold shadow-2xs focus:outline-none cursor-pointer"
          >
            <option value="ALL">All Departments</option>
            <option value="TMS">TMS (Track)</option>
            <option value="SMMS">SMMS (Signal)</option>
            <option value="TDMS">TDMS (Traction)</option>
          </select>
        </div>
      </div>

      {/* Action Banner */}
      {actionSuccess && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 font-semibold flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 font-semibold flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Empty State */}
      {filteredOpportunities.length === 0 ? (
        <div className="py-14 px-4 text-center flex flex-col items-center justify-center border border-slate-200 border-dashed rounded-2xl bg-slate-50/50">
          <div className="p-3.5 rounded-2xl bg-purple-50 text-purple-600 mb-3 border border-purple-100">
            <Sparkles className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-bold text-slate-800">
            No Shadow Opportunities Matching Current Filter
          </h3>
          <p className="text-xs text-slate-500 max-w-md mt-1">
            All active primary possessions are either already synchronized or no candidates meet the selected filter criteria.
          </p>
        </div>
      ) : (
        /* Opportunity Cards Grid */
        <div className="grid grid-cols-1 gap-6">
          {filteredOpportunities.map((opp) => (
            <div
              key={opp.primary_block_id}
              className="border border-slate-200 rounded-2xl bg-white overflow-hidden shadow-xs hover:shadow-sm transition"
            >
              {/* Primary Block Top Bar */}
              <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <div className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
                    PRIMARY POSSESSION
                  </div>
                  <span className="font-extrabold text-sm text-slate-900">
                    {opp.section_code}
                  </span>
                  <span className="text-xs text-slate-500">
                    ({opp.from_station_code} → {opp.to_station_code})
                  </span>
                  <div className="flex items-center gap-1.5 bg-purple-100/70 text-purple-900 border border-purple-200 px-2.5 py-0.5 rounded-md text-xs font-bold shadow-2xs">
                    <Calendar className="w-3.5 h-3.5 text-purple-700" />
                    <span>{formatIsoDate(opp.primary_start)}</span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2.5 text-xs text-slate-700">
                  <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs font-mono text-xs font-semibold">
                    <Clock className="w-3.5 h-3.5 text-amber-600" />
                    <span>
                      {formatIsoTime(opp.primary_start)} – {formatIsoTime(opp.primary_end)} IST ({opp.primary_duration_min}m primary window)
                    </span>
                  </div>
                  <div className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-slate-800 font-bold text-[11px] shadow-2xs flex items-center gap-1">
                    <span className="text-slate-400 font-normal">Primary Host:</span>
                    <span className="text-purple-700 font-extrabold">{opp.primary_source_system || 'TMS'}</span>
                    <span>• {opp.primary_defect_code || 'PRIMARY'}</span>
                  </div>
                </div>
              </div>

              {/* Candidate Cards List */}
              <div className="p-4 flex flex-col gap-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-purple-700 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                  Eligible Piggyback Candidates for this Window ({opp.candidates.length})
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {opp.candidates.map((cand) => {
                    const itemKey = cand.candidate_id || cand.defect_id || cand.block_request_id || cand.defect_code;
                    const key = `${opp.primary_block_id}-${itemKey}`;
                    const isProcessing = processingId === key;
                    const fitPercent = Math.round(cand.duration_fit_ratio * 100);
                    const candDept = cand.department || cand.source_system || 'TMS';
                    const isCrossDept = candDept !== (opp.primary_source_system || 'TMS');
                    const occurrences = defectOpportunityCounts.get(cand.defect_code) || 1;

                    return (
                      <div
                        key={itemKey}
                        className="bg-slate-50/70 border border-slate-200/90 rounded-xl p-4 flex flex-col justify-between gap-3 hover:border-purple-300 hover:bg-white transition"
                      >
                        <div className="flex flex-col gap-2.5">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase ${
                                  candDept === 'SMMS'
                                    ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                    : candDept === 'TDMS'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                }`}
                              >
                                {candDept} CANDIDATE
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-extrabold ${
                                  isCrossDept
                                    ? 'bg-purple-100 text-purple-800 border border-purple-200'
                                    : 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                }`}
                              >
                                {isCrossDept ? `Cross-Dept Piggyback (${candDept} on ${opp.primary_source_system})` : `Intra-Dept Consolidation (${candDept})`}
                              </span>
                              <span className="font-bold text-xs text-slate-900">
                                {cand.defect_code}
                              </span>
                            </div>

                            <div>
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                  cand.criticality_score >= 80
                                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                    : cand.criticality_score >= 60
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                }`}
                              >
                                Score: {cand.criticality_score.toFixed(1)}
                              </span>
                            </div>
                          </div>

                          <div className="text-xs font-bold text-slate-900">
                            {cand.defect_type}
                          </div>

                          {/* Multi-slot info callout if defect fits multiple scheduled dates */}
                          {occurrences > 1 && (
                            <div className="text-[11px] bg-amber-50/90 border border-amber-200 text-amber-900 rounded-lg px-2.5 py-1.5 flex items-start gap-1.5">
                              <Info className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
                              <span>
                                <strong>Alternative Slot:</strong> {cand.defect_code} fits <strong>{occurrences} scheduled primary windows</strong> on this section. Approving this card schedules maintenance specifically on <strong>{formatShortDate(opp.primary_start)}</strong>.
                              </span>
                            </div>
                          )}

                          {/* Dedicated Proposed Shadow Execution Window Box */}
                          <div className="bg-purple-50/60 border border-purple-200/90 rounded-xl p-3 flex flex-col gap-2 shadow-2xs">
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="font-extrabold text-purple-900 flex items-center gap-1.5 uppercase tracking-wide">
                                <Clock className="w-3.5 h-3.5 text-purple-700" />
                                Proposed Execution Window
                              </span>
                              <span className="font-bold text-xs text-purple-800 bg-white px-2 py-0.5 rounded border border-purple-200 shadow-2xs">
                                {cand.estimated_duration_min}m duration
                              </span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 text-xs font-mono font-bold text-slate-800 bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                              <span className="text-slate-600 font-sans font-semibold flex items-center gap-1">
                                <Calendar className="w-3.5 h-3.5 text-purple-600" />
                                {formatIsoDate(opp.primary_start)}:
                              </span>
                              <span className="text-purple-900 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                                {formatIsoTime(opp.primary_start)} IST
                              </span>
                              <span className="text-slate-400">→</span>
                              <span className="text-purple-900 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                                {calculateShadowEndTime(opp.primary_start, cand.estimated_duration_min)} IST
                              </span>
                              <span className="text-[11px] font-sans font-normal text-slate-500 ml-auto">
                                (Within {opp.primary_duration_min}m primary block)
                              </span>
                            </div>

                            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-500 pt-1 border-t border-purple-100">
                              {cand.detected_at && (
                                <span className="flex items-center gap-1">
                                  <span className="font-semibold text-slate-600">Reported/Detected:</span>
                                  <span>{formatIsoDateTime(cand.detected_at)}</span>
                                </span>
                              )}
                              {cand.required_by ? (
                                <span className="flex items-center gap-1 text-rose-600 font-semibold">
                                  <span>Required By:</span>
                                  <span>{formatIsoDateTime(cand.required_by)}</span>
                                </span>
                              ) : (
                                <span className="text-slate-400 italic">No strict deadline (routine maintenance)</span>
                              )}
                            </div>
                          </div>

                          <p className="text-[11px] text-slate-600 line-clamp-2 leading-relaxed">
                            {cand.recommendation_reason}
                          </p>

                          {/* Duration Fit Progress */}
                          <div className="flex flex-col gap-1 pt-1">
                            <div className="flex justify-between text-[10px]">
                              <span className="text-slate-500 font-medium">Needed: <strong>{cand.estimated_duration_min}m</strong></span>
                              <span className="font-bold text-purple-700">
                                {fitPercent}% of primary window
                              </span>
                            </div>
                            <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-purple-500 to-indigo-600 rounded-full"
                                style={{ width: `${Math.min(100, fitPercent)}%` }}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2 pt-3 border-t border-slate-200/80">
                          <button
                            disabled={isProcessing}
                            onClick={() => handleApprove(opp, cand)}
                            className="flex-1 flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold py-2 px-3 rounded-xl shadow-xs transition active:scale-95"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>
                              {isProcessing ? 'Approving...' : `1-Click Approve (${formatShortDate(opp.primary_start)})`}
                            </span>
                          </button>
                          <button
                            disabled={isProcessing}
                            onClick={() => handleDiscard(opp, cand)}
                            className="flex items-center justify-center gap-1 bg-white hover:bg-rose-50 text-slate-600 hover:text-rose-700 border border-slate-300 hover:border-rose-200 disabled:opacity-50 text-xs font-semibold py-2 px-3 rounded-xl transition"
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Discard</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
