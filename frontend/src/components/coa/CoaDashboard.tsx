import React, { useState, useEffect, useCallback } from 'react';
import {
  Station,
  BlockSection,
  TrainMovement,
  CorridorBlock,
  ShadowOpportunity,
  EmergencyIncident,
} from '../../types';
import {
  fetchCorridorStations,
  getCorridorSections,
  fetchCorridorTrains,
  fetchCorridorBlocks,
  fetchShadowOpportunities,
  fetchEmergencyIncidents,
  API_BASE,
} from '../../api/client';
import { CorridorTrackMap } from './CorridorTrackMap';
import { GanttTimeline } from './GanttTimeline';
import { TabularView } from './TabularView';
import { ShadowApprovalPanel } from './ShadowApprovalPanel';
import { EmergencyOperationsCenter } from './EmergencyOperationsCenter';
import { DelayReoptimizeModal } from './DelayReoptimizeModal';
import { OptimizerRunModal } from './OptimizerRunModal';
import {
  Layers,
  MapPin,
  Calendar,
  RefreshCw,
  Sparkles,
  AlertOctagon,
  Cpu,
  GitFork,
  ShieldCheck,
  Train,
  Clock,
  Table,
  CheckCircle2,
} from 'lucide-react';

export const CoaDashboard: React.FC = () => {
  // Navigation tab state - default to 'timeline' for authentic Rail Flow
  const [activeTab, setActiveTab] = useState<'timeline' | 'map' | 'tabular' | 'shadow' | 'emergency'>('timeline');
  const [selectedDate, setSelectedDate] = useState<string>('2026-09-04');
  const [dateScope, setDateScope] = useState<'day' | 'month'>('day');

  // Corridor Data State
  const [stations, setStations] = useState<Station[]>([]);
  const [sections, setSections] = useState<BlockSection[]>([]);
  const [trains, setTrains] = useState<TrainMovement[]>([]);
  const [blocks, setBlocks] = useState<CorridorBlock[]>([]);
  const [shadowOpps, setShadowOpps] = useState<ShadowOpportunity[]>([]);
  const [emergencyCount, setEmergencyCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [corridorError, setCorridorError] = useState<string | null>(null);

  // Modals
  const [isDelayModalOpen, setIsDelayModalOpen] = useState<boolean>(false);
  const [isOptimizerModalOpen, setIsOptimizerModalOpen] = useState<boolean>(false);

  // Load Corridor Data
  const loadCorridorData = useCallback(async () => {
    try {
      setIsLoading(true);
      setCorridorError(null);
      const blkPromise =
        dateScope === 'month'
          ? fetchCorridorBlocks(undefined, '2026-09-01', '2026-09-30')
          : fetchCorridorBlocks(selectedDate);

      const [stnData, secData, trnData, blkData, shdData, emgData] = await Promise.all([
        fetchCorridorStations(),
        getCorridorSections(),
        fetchCorridorTrains(selectedDate),
        blkPromise,
        fetchShadowOpportunities(),
        fetchEmergencyIncidents(),
      ]);

      setStations(stnData);
      setSections(secData);
      setTrains(trnData);
      setBlocks(blkData);
      setShadowOpps(shdData);
      setEmergencyCount(emgData.filter((i: EmergencyIncident) => i.status !== 'released').length);
    } catch (err: any) {
      console.error('Failed to load COA corridor data:', err);
      setCorridorError(err?.message || 'Failed to load corridor data from backend');
    } finally {
      setIsLoading(false);
    }
  }, [selectedDate, dateScope]);

  useEffect(() => {
    loadCorridorData();

    // 15-second background refresh
    const timer = setInterval(() => {
      loadCorridorData();
    }, 15000);

    return () => clearInterval(timer);
  }, [loadCorridorData]);

  // Aggregate Metrics
  const primaryBlocksCount = blocks.filter((b) => b.block_type === 'primary').length;
  const shadowBlocksCount = blocks.filter((b) => b.block_type === 'shadow').length;
  const totalShadowCandidates = shadowOpps.reduce((acc, o) => acc + o.candidates.length, 0);
  const delayedTrainsCount = trains.filter((t) => t.delay_minutes > 0).length;

  return (
    <div className="flex flex-col gap-5">
      {corridorError && (
        <div className="bg-amber-50 border border-amber-300 text-amber-900 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs">
          <div>
            <p className="font-bold text-xs flex items-center gap-1.5">
              <span>⚠️</span>
              Corridor Data Loading Delay / Error
            </p>
            <p className="text-[11px] text-amber-700 mt-0.5">
              Target API: <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-amber-200">{API_BASE || window.location.origin}</code> • Details: {corridorError}
            </p>
          </div>
          <button
            onClick={() => loadCorridorData()}
            className="px-3.5 py-1.5 bg-amber-700 hover:bg-amber-800 text-white rounded-xl text-xs font-bold transition shadow-xs flex-shrink-0"
          >
            Retry Now
          </button>
        </div>
      )}

      {/* Top Banner with KPIs & Controls */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm flex flex-col gap-4 text-slate-800">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-3 bg-gradient-to-br from-indigo-600 to-blue-700 rounded-xl text-white shadow-xs">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
                  COA Master Control Cockpit
                </h1>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase bg-indigo-50 text-indigo-700 border border-indigo-200">
                  VSKP → BZA • 350 KM
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Central Operations & Allocation • Continuous corridor rail flow, Google OR-Tools scheduling & multi-department sync
              </p>
            </div>
          </div>

          {/* Controls: Scope Switcher, Date Picker, Delay Sim, Optimizer Run */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            {/* Scope Toggle: Day vs Sep 1-30 Full Month */}
            <div className="flex items-center bg-slate-100 rounded-xl p-1 border border-slate-200">
              <button
                onClick={() => setDateScope('day')}
                className={`px-3 py-1.5 rounded-lg font-bold transition ${
                  dateScope === 'day'
                    ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Day
              </button>
              <button
                onClick={() => setDateScope('month')}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-bold transition ${
                  dateScope === 'month'
                    ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Calendar className="w-3 h-3 text-indigo-600" />
                <span>Sep 1–30</span>
              </button>
            </div>

            {dateScope === 'day' && (
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="bg-transparent text-slate-700 text-xs font-semibold focus:outline-none"
                />
              </div>
            )}

            <button
              onClick={() => setIsDelayModalOpen(true)}
              className="flex items-center gap-1.5 bg-white hover:bg-slate-50 text-slate-700 font-bold px-3.5 py-2 rounded-xl border border-slate-300 shadow-xs transition"
            >
              <GitFork className="w-3.5 h-3.5 text-indigo-600" />
              <span>Simulate Delay</span>
            </button>

            <button
              onClick={() => setIsOptimizerModalOpen(true)}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded-xl shadow-xs transition active:scale-95"
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>Run CP-SAT Optimizer</span>
            </button>

            <button
              onClick={() => loadCorridorData()}
              className="p-2 bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-900 rounded-xl border border-slate-200 shadow-xs transition"
              title="Refresh Corridor Data"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-indigo-600' : ''}`} />
            </button>
          </div>
        </div>

        {/* 5-Column Live Metric Counters */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 pt-3 border-t border-slate-100">
          <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200/80 flex flex-col shadow-2xs">
            <span className="text-[11px] text-slate-500 font-bold uppercase flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
              Active Possessions
            </span>
            <div className="text-2xl font-black text-slate-900 mt-1">
              {blocks.length}{' '}
              <span className="text-xs font-semibold text-amber-700">
                ({primaryBlocksCount} Prim / {shadowBlocksCount} Shad)
              </span>
            </div>
          </div>

          <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200/80 flex flex-col shadow-2xs">
            <span className="text-[11px] text-slate-500 font-bold uppercase flex items-center gap-1.5">
              <Train className="w-3.5 h-3.5 text-sky-600" />
              Corridor Trains
            </span>
            <div className="text-2xl font-black text-slate-900 mt-1">
              {trains.length}{' '}
              <span className={`text-xs font-semibold ${delayedTrainsCount > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                ({delayedTrainsCount} delayed)
              </span>
            </div>
          </div>

          <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200/80 flex flex-col shadow-2xs">
            <span className="text-[11px] text-slate-500 font-bold uppercase flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              Shadow Piggybacks
            </span>
            <div className="text-2xl font-black text-purple-700 mt-1">
              {totalShadowCandidates}{' '}
              <span className="text-xs font-semibold text-slate-500">candidates</span>
            </div>
          </div>

          <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200/80 flex flex-col shadow-2xs">
            <span className="text-[11px] text-slate-500 font-bold uppercase flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-emerald-600" />
              Block Sections
            </span>
            <div className="text-2xl font-black text-slate-900 mt-1">
              {sections.length}{' '}
              <span className="text-xs font-semibold text-emerald-700">11 UP / 11 DN</span>
            </div>
          </div>

          <div
            onClick={() => setActiveTab('emergency')}
            className={`p-3.5 rounded-xl border flex flex-col cursor-pointer transition shadow-2xs ${
              emergencyCount > 0
                ? 'bg-rose-50 border-rose-300 hover:border-rose-400'
                : 'bg-slate-50/80 border-slate-200/80 hover:border-slate-300'
            }`}
          >
            <span className="text-[11px] font-bold uppercase flex items-center gap-1.5 text-rose-700">
              <AlertOctagon className={`w-3.5 h-3.5 ${emergencyCount > 0 ? 'text-rose-600 animate-pulse' : 'text-slate-400'}`} />
              Emergency Center
            </span>
            <div className={`text-2xl font-black mt-1 ${emergencyCount > 0 ? 'text-rose-700' : 'text-slate-900'}`}>
              {emergencyCount}{' '}
              <span className="text-xs font-semibold">
                {emergencyCount > 0 ? 'Active Alert(s)' : 'Clear'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Tab Switcher Bar */}
      <div className="flex flex-wrap items-center gap-2 bg-slate-100 p-1.5 rounded-2xl border border-slate-200/80 text-xs">
        <button
          onClick={() => setActiveTab('timeline')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold transition-all ${
            activeTab === 'timeline'
              ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/80'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
          }`}
        >
          <Layers className="w-4 h-4 text-indigo-600" />
          <span>Train Rail Flow & String Chart</span>
        </button>

        <button
          onClick={() => setActiveTab('map')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold transition-all ${
            activeTab === 'map'
              ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/80'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
          }`}
        >
          <MapPin className="w-4 h-4 text-sky-600" />
          <span>Track Diagram & 24h Scrubber</span>
        </button>

        <button
          onClick={() => setActiveTab('tabular')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold transition-all ${
            activeTab === 'tabular'
              ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/80'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
          }`}
        >
          <Table className="w-4 h-4 text-slate-600" />
          <span>Operational Records (Tabular)</span>
        </button>

        <button
          onClick={() => setActiveTab('shadow')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold transition-all ${
            activeTab === 'shadow'
              ? 'bg-white text-purple-700 shadow-xs border border-slate-200/80'
              : 'text-slate-600 hover:text-purple-700 hover:bg-slate-200/50'
          }`}
        >
          <Sparkles className="w-4 h-4 text-purple-600" />
          <span>1-Click Shadow Piggybacks</span>
          {totalShadowCandidates > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-purple-100 text-purple-800 border border-purple-200">
              {totalShadowCandidates}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('emergency')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-bold transition-all ${
            activeTab === 'emergency'
              ? 'bg-rose-600 text-white shadow-xs'
              : 'text-rose-700 hover:text-rose-800 hover:bg-rose-50'
          }`}
        >
          <AlertOctagon className="w-4 h-4" />
          <span>Emergency EOC</span>
          {emergencyCount > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-white text-rose-700 border border-rose-300 animate-pulse">
              {emergencyCount} Active
            </span>
          )}
        </button>
      </div>

      {/* Tab Content Display */}
      {activeTab === 'timeline' && (
        <GanttTimeline
          stations={stations}
          sections={sections}
          trains={trains}
          blocks={blocks}
          selectedDate={selectedDate}
        />
      )}

      {activeTab === 'map' && (
        <CorridorTrackMap
          stations={stations}
          sections={sections}
          trains={trains}
          blocks={blocks}
          selectedDate={selectedDate}
        />
      )}

      {activeTab === 'tabular' && (
        <TabularView
          blocks={blocks}
          trains={trains}
          selectedDate={selectedDate}
          dateScope={dateScope}
          onToggleDateScope={(scope) => setDateScope(scope)}
        />
      )}

      {activeTab === 'shadow' && (
        <ShadowApprovalPanel
          opportunities={shadowOpps}
          onRefresh={loadCorridorData}
        />
      )}

      {activeTab === 'emergency' && (
        <EmergencyOperationsCenter
          sections={sections}
          onRefreshCorridor={loadCorridorData}
        />
      )}

      {/* Modals */}
      <DelayReoptimizeModal
        isOpen={isDelayModalOpen}
        onClose={() => setIsDelayModalOpen(false)}
        stations={stations}
        trains={trains}
        selectedDate={selectedDate}
        onSuccess={loadCorridorData}
      />

      <OptimizerRunModal
        isOpen={isOptimizerModalOpen}
        onClose={() => setIsOptimizerModalOpen(false)}
        selectedDate={selectedDate}
        onSuccess={loadCorridorData}
      />
    </div>
  );
};
