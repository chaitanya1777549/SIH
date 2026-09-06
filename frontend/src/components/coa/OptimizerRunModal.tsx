import React, { useState } from 'react';
import { runOptimizer } from '../../api/client';
import { OptimizerResult } from '../../types';
import { Cpu, CheckCircle2, AlertTriangle, RefreshCw, Calendar, ShieldCheck } from 'lucide-react';

interface OptimizerRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedDate: string;
  onSuccess?: () => Promise<void>;
}

export const OptimizerRunModal: React.FC<OptimizerRunModalProps> = ({
  isOpen,
  onClose,
  selectedDate,
  onSuccess,
}) => {
  const [startDate, setStartDate] = useState<string>(selectedDate || '2026-09-04');
  const [endDate, setEndDate] = useState<string>(selectedDate || '2026-09-05');
  const [safetyBufferMin, setSafetyBufferMin] = useState<number>(10);
  const [maxSolveTimeSec, setMaxSolveTimeSec] = useState<number>(30);
  const [isSolving, setIsSolving] = useState<boolean>(false);
  const [result, setResult] = useState<OptimizerResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleRunOptimizer = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSolving(true);
    setErrorMsg(null);
    setResult(null);

    try {
      const res = await runOptimizer(
        startDate,
        endDate,
        safetyBufferMin,
        maxSolveTimeSec
      );
      setResult(res);
      if (onSuccess) await onSuccess();
    } catch (err: any) {
      setErrorMsg(err.message || 'Optimizer run failed');
    } finally {
      setIsSolving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl flex flex-col gap-5 text-white">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/20 text-emerald-400 rounded-lg">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-100 flex items-center gap-2">
                Google OR-Tools CP-SAT Optimizer
              </h3>
              <p className="text-xs text-slate-400">
                Automatic mathematical solver for corridor block requests
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-sm font-semibold p-1"
          >
            ✕
          </button>
        </div>

        {/* Solver Configuration Form */}
        <form onSubmit={handleRunOptimizer} className="flex flex-col gap-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-slate-300 font-semibold">Start Horizon Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-slate-300 font-semibold">End Horizon Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-slate-300 font-semibold">Safety Buffer (Minutes)</label>
              <input
                type="number"
                min={5}
                max={30}
                value={safetyBufferMin}
                onChange={(e) => setSafetyBufferMin(Number(e.target.value))}
                className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-slate-300 font-semibold">Max Solve Time (Sec)</label>
              <input
                type="number"
                min={5}
                max={120}
                value={maxSolveTimeSec}
                onChange={(e) => setMaxSolveTimeSec(Number(e.target.value))}
                className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>
          </div>

          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
            The CP-SAT mathematical solver enforces non-overlapping block possessions, minimum headway intervals between trains, and optimizes objective value weighted by ML criticality scores.
          </div>

          {errorMsg && (
            <div className="p-3 bg-rose-950/80 border border-rose-600/70 rounded-lg text-xs text-rose-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Results Summary */}
          {result && (
            <div className="p-4 bg-emerald-950/40 border border-emerald-600/60 rounded-xl flex flex-col gap-2">
              <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs">
                <CheckCircle2 className="w-4 h-4" />
                Solver Execution Completed ({result.status})
              </div>
              <p className="text-[11px] text-slate-300">{result.message}</p>
              <div className="grid grid-cols-3 gap-2 text-center pt-2 border-t border-emerald-800/40">
                <div className="bg-slate-900/80 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-slate-400">Considered</div>
                  <div className="text-sm font-bold text-slate-200">
                    {result.total_requests_considered}
                  </div>
                </div>
                <div className="bg-slate-900/80 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-emerald-400">Allocated</div>
                  <div className="text-sm font-bold text-emerald-300">
                    {result.allocated_count}
                  </div>
                </div>
                <div className="bg-slate-900/80 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-amber-400">Pending</div>
                  <div className="text-sm font-bold text-amber-300">
                    {result.pending_count}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold px-4 py-2 rounded-lg transition"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={isSolving}
              className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold px-5 py-2 rounded-lg shadow-md transition"
            >
              {isSolving ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Solving Model...
                </>
              ) : (
                <>
                  <Cpu className="w-4 h-4" />
                  Run CP-SAT Solver
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
