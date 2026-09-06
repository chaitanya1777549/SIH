import React, { useState } from 'react';
import { Station, TrainMovement, ReOptimizeResult } from '../../types';
import { simulateDelayAndReoptimize } from '../../api/client';
import {
  GitFork,
  AlertTriangle,
  Clock,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Sliders,
  Sparkles,
  ArrowRight,
} from 'lucide-react';

interface DelayReoptimizeModalProps {
  isOpen: boolean;
  onClose: () => void;
  stations: Station[];
  trains: TrainMovement[];
  selectedDate: string;
  onSuccess?: () => Promise<void>;
}

export const DelayReoptimizeModal: React.FC<DelayReoptimizeModalProps> = ({
  isOpen,
  onClose,
  stations,
  trains,
  selectedDate,
  onSuccess,
}) => {
  // Unique trains for dropdown
  const uniqueTrainNumbers = Array.from(new Set(trains.map((t) => t.train_number))).sort();

  const [selectedTrain, setSelectedTrain] = useState<string>(uniqueTrainNumbers[0] || '12805');
  const [selectedStation, setSelectedStation] = useState<string>(
    stations.length > 0 ? stations[0].station_code : 'VSKP'
  );
  const [delayMinutes, setDelayMinutes] = useState<number>(45);
  const [criticalityThreshold, setCriticalityThreshold] = useState<number>(70);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationResult, setSimulationResult] = useState<ReOptimizeResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSimulate = async () => {
    setIsSimulating(true);
    setErrorMessage(null);
    setSimulationResult(null);

    try {
      const res = await simulateDelayAndReoptimize(
        selectedTrain,
        selectedDate,
        selectedStation,
        delayMinutes,
        criticalityThreshold
      );
      setSimulationResult(res);
      if (onSuccess) await onSuccess();
    } catch (err: any) {
      setErrorMessage(err.message || 'Simulation failed');
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 shadow-2xl flex flex-col gap-5 text-white">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/20 text-indigo-400 rounded-lg">
              <GitFork className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-100 flex items-center gap-2">
                Simulate Train Delay & Re-Optimize Corridor
              </h3>
              <p className="text-xs text-slate-400">
                Inject delay at a station, propagate downstream cascade, and trigger automated conflict resolution
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

        {/* Input Parameters */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs">
          {/* Train Selector */}
          <div className="flex flex-col gap-1.5">
            <label className="text-slate-300 font-semibold">Select Train Number</label>
            <select
              value={selectedTrain}
              onChange={(e) => setSelectedTrain(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              {uniqueTrainNumbers.map((num) => (
                <option key={num} value={num}>
                  Train #{num}
                </option>
              ))}
            </select>
          </div>

          {/* Station Selector */}
          <div className="flex flex-col gap-1.5">
            <label className="text-slate-300 font-semibold">Station Where Delay Injected</label>
            <select
              value={selectedStation}
              onChange={(e) => setSelectedStation(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              {stations.map((s) => (
                <option key={s.station_code} value={s.station_code}>
                  {s.station_code} – {s.station_name}
                </option>
              ))}
            </select>
          </div>

          {/* Delay Minutes */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between">
              <label className="text-slate-300 font-semibold">Injected Delay</label>
              <span className="font-bold text-rose-400">+{delayMinutes} minutes</span>
            </div>
            <input
              type="range"
              min={10}
              max={180}
              step={5}
              value={delayMinutes}
              onChange={(e) => setDelayMinutes(Number(e.target.value))}
              className="w-full accent-rose-500"
            />
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>+10m</span>
              <span>+60m</span>
              <span>+120m</span>
              <span>+180m</span>
            </div>
          </div>

          {/* Criticality Threshold */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between">
              <label className="text-slate-300 font-semibold">Criticality Cutoff Threshold</label>
              <span className="font-bold text-amber-400">{criticalityThreshold} Score</span>
            </div>
            <input
              type="range"
              min={50}
              max={90}
              step={5}
              value={criticalityThreshold}
              onChange={(e) => setCriticalityThreshold(Number(e.target.value))}
              className="w-full accent-amber-500"
            />
            <div className="text-[10px] text-slate-400">
              Blocks with score $\ge {criticalityThreshold}$ preserved (train diverted); otherwise block revoked.
            </div>
          </div>
        </div>

        {/* Error Banner */}
        {errorMessage && (
          <div className="p-3 bg-rose-950/80 border border-rose-600/70 rounded-lg text-xs text-rose-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Simulate Action Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSimulate}
            disabled={isSimulating}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold px-6 py-2.5 rounded-lg shadow-lg transition"
          >
            {isSimulating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Simulating Cascading Delays...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Simulate & Trigger Conflict Resolver
              </>
            )}
          </button>
        </div>

        {/* Results Section */}
        {simulationResult && (
          <div className="flex flex-col gap-4 border-t border-slate-800 pt-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Cascade Re-Optimizer Results
              </span>
              <span className="text-[11px] text-slate-400">
                Train #{simulationResult.train_number} @ {simulationResult.station_code} (+{simulationResult.delay_minutes}m)
              </span>
            </div>

            {/* Metrics Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Conflicts Detected</div>
                <div className="text-xl font-black text-rose-400 mt-0.5">
                  {simulationResult.conflicts_detected}
                </div>
              </div>

              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Trains Diverted</div>
                <div className="text-xl font-black text-sky-400 mt-0.5">
                  {simulationResult.trains_diverted_count}
                </div>
              </div>

              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Blocks Rescheduled</div>
                <div className="text-xl font-black text-amber-400 mt-0.5">
                  {simulationResult.blocks_revoked_count}
                </div>
              </div>
            </div>

            {/* Conflicts Breakdown */}
            {simulationResult.conflict_resolutions && simulationResult.conflict_resolutions.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="text-xs font-semibold text-slate-300">
                  Intelligent Decision Matrix Resolutions:
                </div>
                <div className="flex flex-col gap-2 max-h-44 overflow-y-auto">
                  {simulationResult.conflict_resolutions.map((res: any, idx: number) => {
                    const isDiverted = res.action_taken === 'TRAIN_DIVERTED' || res.decision === 'DIVERT_TRAIN';
                    return (
                      <div
                        key={idx}
                        className="bg-slate-950 p-3 rounded-lg border border-slate-800 flex flex-col gap-1 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-200">
                            Section: {res.section_code || 'CORRIDOR'}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              isDiverted
                                ? 'bg-sky-900/60 text-sky-300 border border-sky-700/60'
                                : 'bg-amber-900/60 text-amber-300 border border-amber-700/60'
                            }`}
                          >
                            {isDiverted ? 'TRAIN DIVERTED (BLOCK PRESERVED)' : 'BLOCK REVOKED & RESCHEDULED'}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400">
                          {res.explanation || res.reason || 'Conflict resolved according to ML safety priority threshold.'}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
