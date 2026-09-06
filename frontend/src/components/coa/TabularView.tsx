import React, { useState, useMemo } from 'react';
import { CorridorBlock, TrainMovement } from '../../types';
import { Table, Search, ShieldCheck, Sparkles, Train, ArrowUpDown, Clock, Download, Calendar } from 'lucide-react';

interface TabularViewProps {
  blocks: CorridorBlock[];
  trains: TrainMovement[];
  selectedDate: string;
  dateScope?: 'day' | 'month';
  onToggleDateScope?: (scope: 'day' | 'month') => void;
}

export const TabularView: React.FC<TabularViewProps> = ({
  blocks,
  trains,
  selectedDate,
  dateScope = 'day',
  onToggleDateScope,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'blocks' | 'trains'>('blocks');

  // Blocks Filters
  const [blockSearch, setBlockSearch] = useState('');
  const [blockTypeFilter, setBlockTypeFilter] = useState<'ALL' | 'primary' | 'shadow'>('ALL');
  const [blockDeptFilter, setBlockDeptFilter] = useState<string>('ALL');

  // Trains Filters
  const [trainSearch, setTrainSearch] = useState('');
  const [trainDelayFilter, setTrainDelayFilter] = useState<'ALL' | 'delayed' | 'ontime'>('ALL');

  // Filtered Blocks
  const filteredBlocks = useMemo(() => {
    return blocks.filter((b) => {
      if (blockTypeFilter !== 'ALL' && b.block_type !== blockTypeFilter) return false;
      if (blockDeptFilter !== 'ALL' && b.source_system !== blockDeptFilter) return false;
      if (!blockSearch) return true;
      const q = blockSearch.toLowerCase();
      return (
        b.section_code?.toLowerCase().includes(q) ||
        b.defect_code?.toLowerCase().includes(q) ||
        b.defect_type?.toLowerCase().includes(q) ||
        b.id.toLowerCase().includes(q)
      );
    });
  }, [blocks, blockTypeFilter, blockDeptFilter, blockSearch]);

  // Filtered Trains
  const filteredTrains = useMemo(() => {
    return trains.filter((t) => {
      if (trainDelayFilter === 'delayed' && t.delay_minutes <= 0) return false;
      if (trainDelayFilter === 'ontime' && t.delay_minutes > 0) return false;
      if (!trainSearch) return true;
      const q = trainSearch.toLowerCase();
      return (
        t.train_number.toLowerCase().includes(q) ||
        t.train_name?.toLowerCase().includes(q) ||
        t.section_code.toLowerCase().includes(q)
      );
    });
  }, [trains, trainDelayFilter, trainSearch]);

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
      return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
    } catch {
      return '';
    }
  };

  const exportBlocksToCsv = () => {
    const headers = [
      'Index',
      'Block ID',
      'Date',
      'Type',
      'Section',
      'Department',
      'Defect Code',
      'Defect Type',
      'Planned Start',
      'Planned End',
      'Duration (min)',
      'Criticality',
      'Status',
    ];
    const rows = filteredBlocks.map((b, idx) => [
      idx + 1,
      b.id,
      b.planned_start ? b.planned_start.slice(0, 10) : '',
      b.block_type,
      b.section_code,
      b.source_system || 'ENG',
      b.defect_code || 'SCHEDULED',
      b.defect_type || 'Track Renewal',
      b.planned_start || '',
      b.planned_end || '',
      b.duration_min,
      b.criticality_score || '',
      b.status,
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((r) => r.map((cell) => `"${cell}"`).join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `corridor_allocated_blocks_${dateScope === 'month' ? 'Sep_2026_Month' : selectedDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm flex flex-col gap-4 text-slate-800">
      {/* Sub-Tab Navigation Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-50 text-indigo-700 rounded-xl border border-indigo-100">
            <Table className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-extrabold tracking-tight text-slate-900">
                Corridor Operational Records
              </h2>
              {dateScope === 'month' ? (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-bold border border-indigo-200 flex items-center gap-1">
                  <Calendar className="w-3 h-3 text-indigo-600" />
                  Sep 1 – Sep 30, 2026 (All Corridor Blocks)
                </span>
              ) : (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold border border-slate-200">
                  {selectedDate}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Detailed registry of scheduled/active track possessions and train timetable movements
            </p>
          </div>
        </div>

        {/* Tab Switcher & Scope Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          {onToggleDateScope && (
            <div className="flex items-center bg-slate-100 rounded-xl p-1 border border-slate-200 text-xs">
              <button
                onClick={() => onToggleDateScope('day')}
                className={`px-3 py-1.5 rounded-lg font-bold transition ${
                  dateScope === 'day'
                    ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Day ({selectedDate})
              </button>
              <button
                onClick={() => onToggleDateScope('month')}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg font-bold transition ${
                  dateScope === 'month'
                    ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Calendar className="w-3 h-3 text-indigo-600" />
                <span>Sep 1–30 (Full Month)</span>
              </button>
            </div>
          )}

          <div className="flex items-center bg-slate-100 rounded-xl p-1 border border-slate-200 text-xs">
            <button
              onClick={() => setActiveSubTab('blocks')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-bold transition ${
                activeSubTab === 'blocks'
                  ? 'bg-white text-amber-800 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
              <span>Corridor Blocks ({blocks.length})</span>
            </button>
            <button
              onClick={() => setActiveSubTab('trains')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-bold transition ${
                activeSubTab === 'trains'
                  ? 'bg-white text-sky-800 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Train className="w-3.5 h-3.5 text-sky-600" />
              <span>Train Timetable ({trains.length})</span>
            </button>
          </div>
        </div>
      </div>

      {/* BLOCKS VIEW */}
      {activeSubTab === 'blocks' && (
        <div className="flex flex-col gap-3">
          {/* Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search by section, defect code, defect type..."
                  value={blockSearch}
                  onChange={(e) => setBlockSearch(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl pl-9 pr-3 py-2 focus:outline-none focus:border-indigo-500 focus:bg-white transition"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={blockTypeFilter}
                onChange={(e) => setBlockTypeFilter(e.target.value as any)}
                className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl px-3 py-2 font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                <option value="ALL">All Types (Primary & Shadow)</option>
                <option value="primary">Primary Only</option>
                <option value="shadow">Shadow (Piggyback) Only</option>
              </select>

              <select
                value={blockDeptFilter}
                onChange={(e) => setBlockDeptFilter(e.target.value)}
                className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl px-3 py-2 font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                <option value="ALL">All Departments</option>
                <option value="TMS">TMS (Track)</option>
                <option value="SMMS">SMMS (Signal)</option>
                <option value="TDMS">TDMS (Traction/OHE)</option>
              </select>

              <button
                onClick={exportBlocksToCsv}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-slate-700 font-bold border border-slate-200 transition"
                title="Download CSV report of currently filtered blocks"
              >
                <Download className="w-3.5 h-3.5 text-slate-600" />
                <span>Export CSV</span>
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] tracking-wider font-bold border-b border-slate-200">
                <tr>
                  <th className="py-3 px-3.5">Date</th>
                  <th className="py-3 px-3.5">Type</th>
                  <th className="py-3 px-3.5">Section</th>
                  <th className="py-3 px-3.5">Dept</th>
                  <th className="py-3 px-3.5">Defect Code & Type</th>
                  <th className="py-3 px-3.5">Planned Window</th>
                  <th className="py-3 px-3.5 text-center">Duration</th>
                  <th className="py-3 px-3.5 text-center">Criticality</th>
                  <th className="py-3 px-3.5 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {filteredBlocks.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-slate-400">
                      No corridor blocks match the current filter.
                    </td>
                  </tr>
                ) : (
                  filteredBlocks.map((b) => {
                    const isShadow = b.block_type === 'shadow';
                    return (
                      <tr
                        key={b.id}
                        className="hover:bg-slate-50/80 transition-colors"
                      >
                        <td className="py-3 px-3.5 font-bold text-slate-800 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[11px] font-mono border border-slate-200">
                            {formatIsoDate(b.planned_start)}
                          </span>
                        </td>
                        <td className="py-3 px-3.5">
                          {isShadow ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                              <Sparkles className="w-3 h-3" />
                              SHADOW
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                              <ShieldCheck className="w-3 h-3" />
                              PRIMARY
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3.5 font-bold text-slate-900">
                          {b.section_code}
                        </td>
                        <td className="py-3 px-3.5">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                            {b.source_system || 'TMS'}
                          </span>
                        </td>
                        <td className="py-3 px-3.5">
                          <div className="font-semibold text-slate-900">
                            {b.defect_code || 'SCHEDULED'}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {b.defect_type || 'Track Renewal'}
                          </div>
                        </td>
                        <td className="py-3 px-3.5 text-slate-700 font-mono text-xs whitespace-nowrap">
                          {formatIsoTime(b.planned_start)} – {formatIsoTime(b.planned_end)}
                        </td>
                        <td className="py-3 px-3.5 text-center font-bold text-slate-800">
                          {b.duration_min}m
                        </td>
                        <td className="py-3 px-3.5 text-center">
                          {b.criticality_score ? (
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                b.criticality_score >= 80
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : b.criticality_score >= 60
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              }`}
                            >
                              {b.criticality_score.toFixed(1)}
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-3.5 text-center">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${
                              b.status === 'active'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-slate-100 text-slate-600 border border-slate-200'
                            }`}
                          >
                            {b.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TRAINS TIMETABLE VIEW */}
      {activeSubTab === 'trains' && (
        <div className="flex flex-col gap-3">
          {/* Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search by train number, train name, section..."
                  value={trainSearch}
                  onChange={(e) => setTrainSearch(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl pl-9 pr-3 py-2 focus:outline-none focus:border-indigo-500 focus:bg-white transition"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={trainDelayFilter}
                onChange={(e) => setTrainDelayFilter(e.target.value as any)}
                className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl px-3 py-2 font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer"
              >
                <option value="ALL">All Train Paths</option>
                <option value="delayed">Delayed Movements Only</option>
                <option value="ontime">On-Time Movements Only</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-600 uppercase text-[10px] tracking-wider font-bold border-b border-slate-200">
                <tr>
                  <th className="py-3 px-3.5">Train</th>
                  <th className="py-3 px-3.5">Section</th>
                  <th className="py-3 px-3.5">Scheduled Window</th>
                  <th className="py-3 px-3.5">Forecast Entry / Exit</th>
                  <th className="py-3 px-3.5 text-center">Delay</th>
                  <th className="py-3 px-3.5 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {filteredTrains.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-400">
                      No train movements match the current filter.
                    </td>
                  </tr>
                ) : (
                  filteredTrains.map((t) => {
                    const isDelayed = t.delay_minutes > 0;
                    return (
                      <tr
                        key={t.id}
                        className="hover:bg-slate-50/80 transition-colors"
                      >
                        <td className="py-3 px-3.5">
                          <div className="font-bold text-slate-900 flex items-center gap-1.5">
                            <Train className="w-3.5 h-3.5 text-indigo-600" />
                            #{t.train_number}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {t.train_name || 'Passenger / Express'}
                          </div>
                        </td>
                        <td className="py-3 px-3.5 font-semibold text-slate-800">
                          {t.section_code}
                        </td>
                        <td className="py-3 px-3.5 text-slate-600 font-mono text-xs">
                          {formatIsoTime(t.scheduled_entry)} – {formatIsoTime(t.scheduled_exit)}
                        </td>
                        <td className="py-3 px-3.5 text-slate-800 font-mono text-xs font-semibold">
                          {formatIsoTime(t.forecast_entry)} – {formatIsoTime(t.forecast_exit)}
                        </td>
                        <td className="py-3 px-3.5 text-center">
                          {isDelayed ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                              +{t.delay_minutes}m
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              On Time
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3.5 text-center">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${
                              isDelayed
                                ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}
                          >
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
