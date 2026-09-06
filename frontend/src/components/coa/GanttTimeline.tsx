import React, { useState, useMemo, useRef } from 'react';
import { Station, BlockSection, TrainMovement, CorridorBlock } from '../../types';
import {
  Layers,
  Info,
  ShieldCheck,
  Train,
  Sparkles,
  GitBranch,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Search,
  Filter,
  ZoomIn,
  ZoomOut,
  Maximize2,
  X,
  AlertTriangle,
  ChevronRight,
  Calendar,
} from 'lucide-react';

interface GanttTimelineProps {
  stations?: Station[];
  sections: BlockSection[];
  trains: TrainMovement[];
  blocks: CorridorBlock[];
  selectedDate: string;
}

interface HoverItem {
  type: 'train' | 'primary_block' | 'shadow_block' | 'free_gap';
  data: any;
  x: number;
  y: number;
}

interface CorridorTrainPath {
  trainNumber: string;
  trainName: string;
  trainType: string;
  direction: 'UP' | 'DN';
  isDelayed: boolean;
  maxDelay: number;
  movements: TrainMovement[];
  points: { x: number; y: number; stationCode: string; timeMin: number; action: 'entry' | 'exit' }[];
  originStation: string;
  destStation: string;
  startTime: string;
  endTime: string;
}

const DEFAULT_STATIONS: { code: string; name: string; km: number }[] = [
  { code: 'VSKP', name: 'Visakhapatnam Jn', km: 0 },
  { code: 'DVD', name: 'Duvvada', km: 17 },
  { code: 'AKP', name: 'Anakapalle', km: 40 },
  { code: 'TUNI', name: 'Tuni', km: 100 },
  { code: 'ANV', name: 'Annavaram', km: 130 },
  { code: 'SLO', name: 'Samalkot Jn', km: 160 },
  { code: 'APT', name: 'Anaparti', km: 180 },
  { code: 'RJY', name: 'Rajahmundry', km: 210 },
  { code: 'NDD', name: 'Nidadavolu Jn', km: 250 },
  { code: 'TDD', name: 'Tadepalligudem', km: 280 },
  { code: 'EE', name: 'Eluru', km: 310 },
  { code: 'BZA', name: 'Vijayawada Jn', km: 350 },
];

export const GanttTimeline: React.FC<GanttTimelineProps> = ({
  stations = [],
  sections,
  trains,
  blocks,
  selectedDate,
}) => {
  // Primary View Mode: 'string' (Marey Rail Flow Chart) vs 'lanes' (Section Gantt)
  const [viewMode, setViewMode] = useState<'string' | 'lanes'>('string');
  const [directionFilter, setDirectionFilter] = useState<'ALL' | 'UP' | 'DN'>('ALL');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'delayed' | 'ontime'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [hoveredTrainNumber, setHoveredTrainNumber] = useState<string | null>(null);
  const [selectedTrain, setSelectedTrain] = useState<CorridorTrainPath | null>(null);
  const [hoverItem, setHoverItem] = useState<HoverItem | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Time conversion: ISO string to minutes from 00:00 (0 - 1440)
  const toMinutes = (isoString?: string): number => {
    if (!isoString) return 0;
    try {
      const d = new Date(isoString);
      return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
    } catch {
      return 0;
    }
  };

  const formatMins = (mins: number) => {
    const h = String(Math.floor(mins / 60)).padStart(2, '0');
    const m = String(Math.floor(mins % 60)).padStart(2, '0');
    return `${h}:${m}`;
  };

  // Station Geography: Align 12 corridor stations geographically VSKP -> BZA
  const corridorStations = useMemo(() => {
    if (stations && stations.length > 0) {
      return [...stations]
        .sort((a, b) => a.sequence_on_corridor - b.sequence_on_corridor)
        .map((s, idx) => ({
          code: s.station_code,
          name: s.station_name || s.station_code,
          km: s.distance_from_origin_km ?? DEFAULT_STATIONS[idx]?.km ?? idx * 30,
        }));
    }
    return DEFAULT_STATIONS;
  }, [stations]);

  // Station Y-coordinate mapping for String Chart
  const STATION_ROW_HEIGHT = 48;
  const STRING_HEADER_HEIGHT = 40;
  const STATION_COL_WIDTH = 180;
  const BASE_TIMELINE_WIDTH = 1350;
  const TIMELINE_WIDTH = BASE_TIMELINE_WIDTH * zoomLevel;
  const TOTAL_STRING_WIDTH = STATION_COL_WIDTH + TIMELINE_WIDTH;
  const TOTAL_STRING_HEIGHT = STRING_HEADER_HEIGHT + corridorStations.length * STATION_ROW_HEIGHT + 30;

  // Station Code to Y coordinate center
  const stationYMap = useMemo(() => {
    const map = new Map<string, number>();
    corridorStations.forEach((stn, idx) => {
      const y = STRING_HEADER_HEIGHT + idx * STATION_ROW_HEIGHT + STATION_ROW_HEIGHT / 2;
      map.set(stn.code, y);
    });
    return map;
  }, [corridorStations]);

  // Time to X coordinate mapping
  const minToX = (min: number) => {
    const clamped = Math.min(1440, Math.max(0, min));
    return (clamped / 1440) * TIMELINE_WIDTH;
  };

  // Build Continuous Corridor Train Paths (String Chart Trajectories)
  const trainPaths: CorridorTrainPath[] = useMemo(() => {
    const grouped = new Map<string, TrainMovement[]>();
    trains.forEach((t) => {
      const list = grouped.get(t.train_number) || [];
      list.push(t);
      grouped.set(t.train_number, list);
    });

    const paths: CorridorTrainPath[] = [];

    grouped.forEach((movements, trainNum) => {
      // Sort movements chronologically
      movements.sort((a, b) => {
        const ta = new Date(a.forecast_entry || a.scheduled_entry).getTime();
        const tb = new Date(b.forecast_entry || b.scheduled_entry).getTime();
        return ta - tb;
      });

      const firstMov = movements[0];
      const lastMov = movements[movements.length - 1];

      // Determine Direction
      const isUp = movements.some((m) => m.section_code?.includes('UP'));
      const direction: 'UP' | 'DN' = isUp ? 'UP' : 'DN';

      // Determine Delay
      const maxDelay = Math.max(...movements.map((m) => m.delay_minutes || 0));
      const isDelayed = maxDelay > 0;

      // Extract Points across stations
      const points: { x: number; y: number; stationCode: string; timeMin: number; action: 'entry' | 'exit' }[] = [];

      movements.forEach((m) => {
        // Section code parsing: e.g. "VSKP-DVD-DN" or "APT-SLO-UP"
        const parts = m.section_code ? m.section_code.split('-') : [];
        let fromCode = parts[0] || '';
        let toCode = parts[1] || '';

        const entryMin = toMinutes(m.forecast_entry || m.scheduled_entry);
        const exitMin = toMinutes(m.forecast_exit || m.scheduled_exit);

        const yFrom = stationYMap.get(fromCode);
        const yTo = stationYMap.get(toCode);

        if (yFrom !== undefined && entryMin > 0) {
          points.push({
            x: STATION_COL_WIDTH + minToX(entryMin),
            y: yFrom,
            stationCode: fromCode,
            timeMin: entryMin,
            action: 'entry',
          });
        }
        if (yTo !== undefined && exitMin > 0) {
          points.push({
            x: STATION_COL_WIDTH + minToX(exitMin),
            y: yTo,
            stationCode: toCode,
            timeMin: exitMin,
            action: 'exit',
          });
        }
      });

      // Deduplicate consecutive points at same station
      const cleanedPoints = points.filter((p, i) => {
        if (i === 0) return true;
        const prev = points[i - 1];
        return !(prev.stationCode === p.stationCode && Math.abs(prev.x - p.x) < 2);
      });

      if (cleanedPoints.length >= 2) {
        paths.push({
          trainNumber: trainNum,
          trainName: firstMov.train_name || `Train #${trainNum}`,
          trainType: firstMov.train_type || 'Superfast',
          direction,
          isDelayed,
          maxDelay,
          movements,
          points: cleanedPoints,
          originStation: cleanedPoints[0]?.stationCode || '',
          destStation: cleanedPoints[cleanedPoints.length - 1]?.stationCode || '',
          startTime: firstMov.forecast_entry || firstMov.scheduled_entry,
          endTime: lastMov.forecast_exit || lastMov.scheduled_exit,
        });
      }
    });

    return paths;
  }, [trains, stationYMap, zoomLevel]);

  // Filtered Train Paths
  const filteredTrainPaths = useMemo(() => {
    return trainPaths.filter((p) => {
      if (directionFilter !== 'ALL' && p.direction !== directionFilter) return false;
      if (statusFilter === 'delayed' && !p.isDelayed) return false;
      if (statusFilter === 'ontime' && p.isDelayed) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          p.trainNumber.toLowerCase().includes(q) ||
          p.trainName.toLowerCase().includes(q) ||
          p.originStation.toLowerCase().includes(q) ||
          p.destStation.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [trainPaths, directionFilter, statusFilter, searchQuery]);

  // Section Blocks formatted for String Chart possession windows
  const blockWindows = useMemo(() => {
    return blocks
      .filter((b) => !b.planned_start || b.planned_start.startsWith(selectedDate))
      .map((b) => {
      const parts = b.section_code ? b.section_code.split('-') : [];
      const stn1 = parts[0] || '';
      const stn2 = parts[1] || '';
      const isUp = b.section_code?.includes('UP');

      const y1 = stationYMap.get(stn1);
      const y2 = stationYMap.get(stn2);

      const startMin = toMinutes(b.planned_start);
      const rawEndMin = toMinutes(b.planned_end);
      // If block crosses midnight, on this day it runs until 24:00 (1440 min)
      const effectiveEndMin = rawEndMin < startMin ? 1440 : rawEndMin;
      const startX = STATION_COL_WIDTH + minToX(startMin);
      const endX = STATION_COL_WIDTH + minToX(effectiveEndMin);
      const width = Math.max(14, endX - startX);

      let topY = 0;
      let height = 30;
      if (y1 !== undefined && y2 !== undefined) {
        topY = Math.min(y1, y2) - 8;
        height = Math.abs(y2 - y1) + 16;
      } else if (y1 !== undefined) {
        topY = y1 - 15;
        height = 30;
      }

      const totalDurationMin = b.duration_min || Math.round((new Date(b.planned_end).getTime() - new Date(b.planned_start).getTime()) / 60000);

      return {
        block: b,
        startX,
        width,
        topY,
        height,
        stn1,
        stn2,
        isUp,
        isShadow: b.block_type === 'shadow',
        durationMin: totalDurationMin,
      };
    });
  }, [blocks, stationYMap, zoomLevel, selectedDate]);

  // Jump to specific hour in scroll container
  const jumpToHour = (hour: number) => {
    if (containerRef.current) {
      const targetX = minToX(hour * 60) - 100;
      containerRef.current.scrollTo({ left: Math.max(0, targetX), behavior: 'smooth' });
    }
  };

  // Hour markers: 00:00 to 24:00
  const hourTicks = Array.from({ length: 25 }, (_, i) => i);

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm flex flex-col gap-4 text-slate-800">
      {/* 1. Header Toolbar & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl border border-indigo-100">
            <Train className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-extrabold tracking-tight text-slate-900">
                Corridor Train Rail Flow & String Chart
              </h2>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold border border-slate-200">
                {selectedDate}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Continuous rail trajectories across 12 stations (VSKP 0 km → BZA 350 km) • Non-overlapping block possession windows
            </p>
          </div>
        </div>

        {/* View Mode Switcher & Filters */}
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          {/* View Mode Toggle */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setViewMode('string')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold transition-all ${
                viewMode === 'string'
                  ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <GitBranch className="w-3.5 h-3.5" />
              <span>Corridor String Flow</span>
            </button>
            <button
              onClick={() => setViewMode('lanes')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold transition-all ${
                viewMode === 'lanes'
                  ? 'bg-white text-indigo-700 shadow-xs border border-slate-200/60'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Section Track Flow</span>
            </button>
          </div>

          {/* Direction Filter */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setDirectionFilter('ALL')}
              className={`px-2.5 py-1 rounded-lg font-semibold transition ${
                directionFilter === 'ALL' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setDirectionFilter('DN')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg font-semibold transition ${
                directionFilter === 'DN' ? 'bg-white text-sky-700 shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              <ArrowDownRight className="w-3 h-3 text-sky-600" />
              <span>Down (to BZA)</span>
            </button>
            <button
              onClick={() => setDirectionFilter('UP')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg font-semibold transition ${
                directionFilter === 'UP' ? 'bg-white text-purple-700 shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              <ArrowUpRight className="w-3 h-3 text-purple-600" />
              <span>Up (to VSKP)</span>
            </button>
          </div>

          {/* Status Filter */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setStatusFilter('ALL')}
              className={`px-2.5 py-1 rounded-lg font-semibold transition ${
                statusFilter === 'ALL' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              All Trains
            </button>
            <button
              onClick={() => setStatusFilter('delayed')}
              className={`px-2.5 py-1 rounded-lg font-semibold transition ${
                statusFilter === 'delayed' ? 'bg-white text-rose-700 shadow-xs font-bold' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              ⚠️ Delayed Only
            </button>
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
            <input
              type="text"
              placeholder="Search train / stn..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl pl-8 pr-3 py-1.5 w-36 focus:outline-none focus:border-indigo-500 focus:bg-white transition"
            />
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setZoomLevel((z) => Math.max(0.75, z - 0.25))}
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded transition"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] font-bold text-slate-700 px-1">
              {Math.round(zoomLevel * 100)}%
            </span>
            <button
              onClick={() => setZoomLevel((z) => Math.min(2.5, z + 0.25))}
              className="p-1 text-slate-600 hover:text-slate-900 hover:bg-white rounded transition"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 2. Sub-Toolbar: Quick Time Jumps & Legend */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-slate-50 p-2.5 rounded-xl border border-slate-200/80">
        {/* Quick Time Navigation Jumps */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500 font-semibold flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            Jump To:
          </span>
          <button
            onClick={() => jumpToHour(6)}
            className="px-2 py-1 bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 rounded-lg border border-slate-200 font-medium transition"
          >
            🌅 06:00 Morning
          </button>
          <button
            onClick={() => jumpToHour(12)}
            className="px-2 py-1 bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 rounded-lg border border-slate-200 font-medium transition"
          >
            ☀️ 12:00 Noon
          </button>
          <button
            onClick={() => jumpToHour(18)}
            className="px-2 py-1 bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 rounded-lg border border-slate-200 font-medium transition"
          >
            🌆 18:00 Evening
          </button>
          <button
            onClick={() => jumpToHour(0)}
            className="px-2 py-1 bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 rounded-lg border border-slate-200 font-medium transition"
          >
            🌙 00:00 Midnight
          </button>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-slate-600">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-1 bg-sky-600 rounded-full" />
            <span className="text-[11px] font-medium">Down Trains (VSKP → BZA)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-1 bg-indigo-600 rounded-full" />
            <span className="text-[11px] font-medium">Up Trains (BZA → VSKP)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-1.5 bg-rose-600 rounded-full" />
            <span className="text-[11px] font-bold text-rose-700">Delayed Path</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3.5 h-2.5 bg-amber-100 border border-amber-500 rounded" />
            <span className="text-[11px] font-medium">Primary Block Possession</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3.5 h-2.5 bg-purple-100 border border-purple-500 rounded" />
            <span className="text-[11px] font-medium">Shadow Piggyback</span>
          </div>
        </div>
      </div>

      {/* 3. Main Chart Canvas Scroll Area */}
      <div
        ref={containerRef}
        className="relative overflow-x-auto overflow-y-auto max-h-[640px] border border-slate-200/90 rounded-xl bg-slate-50/50 shadow-inner scrollbar-thin"
      >
        {viewMode === 'string' ? (
          /* ========================================================================= */
          /* MODE 1: INDIAN RAILWAYS CORRIDOR STRING FLOW (MAREY TIME-DISTANCE DIAGRAM) */
          /* ========================================================================= */
          <svg
            width={TOTAL_STRING_WIDTH}
            height={TOTAL_STRING_HEIGHT}
            className="select-none font-sans bg-white"
          >
            <defs>
              {/* Pattern for Primary Maintenance Block Window */}
              <pattern id="amberHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="8" height="8" fill="#fef3c7" />
                <line x1="0" y1="0" x2="0" y2="8" stroke="#f59e0b" strokeWidth="2.5" />
              </pattern>
              {/* Pattern for Shadow Maintenance Block Window */}
              <pattern id="purpleHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="8" height="8" fill="#f3e8ff" />
                <line x1="0" y1="0" x2="0" y2="8" stroke="#9333ea" strokeWidth="2.5" />
              </pattern>
              {/* Subtle shadow filter */}
              <filter id="stringShadow" x="-10%" y="-10%" width="120%" height="120%">
                <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#000000" floodOpacity="0.15" />
              </filter>
            </defs>

            {/* Time Header Background */}
            <rect x={0} y={0} width={TOTAL_STRING_WIDTH} height={STRING_HEADER_HEIGHT} fill="#f8fafc" />
            <line
              x1={0}
              y1={STRING_HEADER_HEIGHT}
              x2={TOTAL_STRING_WIDTH}
              y2={STRING_HEADER_HEIGHT}
              stroke="#e2e8f0"
              strokeWidth="1.5"
            />

            {/* Left Header Title */}
            <text
              x={16}
              y={24}
              fill="#475569"
              fontSize="11"
              fontWeight="bold"
              letterSpacing="0.05em"
            >
              CORRIDOR STATIONS (12)
            </text>

            {/* Vertical Time Grid Lines (00:00 to 24:00) */}
            {hourTicks.map((hour) => {
              const x = STATION_COL_WIDTH + minToX(hour * 60);
              const isMajor = hour % 3 === 0;
              return (
                <g key={`hour-grid-${hour}`}>
                  <line
                    x1={x}
                    y1={STRING_HEADER_HEIGHT}
                    x2={x}
                    y2={TOTAL_STRING_HEIGHT}
                    stroke={isMajor ? '#cbd5e1' : '#f1f5f9'}
                    strokeWidth={isMajor ? '1' : '0.8'}
                    strokeDasharray={isMajor ? undefined : '3,3'}
                  />
                  {/* Time label at top ruler */}
                  <text
                    x={x}
                    y={24}
                    fill={isMajor ? '#0f172a' : '#64748b'}
                    fontSize={isMajor ? '11' : '10'}
                    fontWeight={isMajor ? 'bold' : 'normal'}
                    textAnchor="middle"
                  >
                    {String(hour).padStart(2, '0')}:00
                  </text>
                </g>
              );
            })}

            {/* Horizontal Station Track Lines & Station Labels */}
            {corridorStations.map((stn, idx) => {
              const y = STRING_HEADER_HEIGHT + idx * STATION_ROW_HEIGHT + STATION_ROW_HEIGHT / 2;
              const isTerminal = idx === 0 || idx === corridorStations.length - 1;

              return (
                <g key={`station-${stn.code}`}>
                  {/* Alternating subtle station row background */}
                  {idx % 2 === 0 && (
                    <rect
                      x={STATION_COL_WIDTH}
                      y={STRING_HEADER_HEIGHT + idx * STATION_ROW_HEIGHT}
                      width={TIMELINE_WIDTH}
                      height={STATION_ROW_HEIGHT}
                      fill="#fafafa"
                      opacity="0.6"
                    />
                  )}

                  {/* Horizontal Railway Track Line */}
                  <line
                    x1={STATION_COL_WIDTH}
                    y1={y}
                    x2={TOTAL_STRING_WIDTH}
                    y2={y}
                    stroke={isTerminal ? '#94a3b8' : '#e2e8f0'}
                    strokeWidth={isTerminal ? '1.5' : '1'}
                  />

                  {/* Sticky Station Label Background */}
                  <rect
                    x={0}
                    y={STRING_HEADER_HEIGHT + idx * STATION_ROW_HEIGHT}
                    width={STATION_COL_WIDTH}
                    height={STATION_ROW_HEIGHT}
                    fill="#ffffff"
                  />
                  <line
                    x1={STATION_COL_WIDTH}
                    y1={STRING_HEADER_HEIGHT + idx * STATION_ROW_HEIGHT}
                    x2={STATION_COL_WIDTH}
                    y2={STRING_HEADER_HEIGHT + (idx + 1) * STATION_ROW_HEIGHT}
                    stroke="#e2e8f0"
                    strokeWidth="1.5"
                  />
                  <line
                    x1={0}
                    y1={STRING_HEADER_HEIGHT + (idx + 1) * STATION_ROW_HEIGHT}
                    x2={STATION_COL_WIDTH}
                    y2={STRING_HEADER_HEIGHT + (idx + 1) * STATION_ROW_HEIGHT}
                    stroke="#f1f5f9"
                    strokeWidth="1"
                  />

                  {/* Station Bullet Indicator */}
                  <circle
                    cx={18}
                    cy={y}
                    r={isTerminal ? 5 : 3.5}
                    fill={isTerminal ? '#4338ca' : '#64748b'}
                  />

                  {/* Station Code & Name */}
                  <text
                    x={30}
                    y={y - 3}
                    fill="#0f172a"
                    fontSize="11.5"
                    fontWeight="bold"
                  >
                    {stn.code}
                  </text>
                  <text
                    x={30}
                    y={y + 11}
                    fill="#64748b"
                    fontSize="9"
                  >
                    {stn.name.length > 14 ? `${stn.name.slice(0, 14)}...` : stn.name} • {stn.km} km
                  </text>
                </g>
              );
            })}

            {/* ========================================================================= */}
            {/* LAYER 1: TRACK MAINTENANCE POSSESSION WINDOWS (BLOCKS)                     */}
            {/* ========================================================================= */}
            {blockWindows.map((bw, bIdx) => (
              <g
                key={`block-win-${bIdx}`}
                className="cursor-pointer hover:opacity-95"
                onMouseEnter={(e) =>
                  setHoverItem({
                    type: bw.isShadow ? 'shadow_block' : 'primary_block',
                    data: bw.block,
                    x: e.clientX,
                    y: e.clientY,
                  })
                }
                onMouseLeave={() => setHoverItem(null)}
              >
                {/* Shaded Track Possession Window */}
                <rect
                  x={bw.startX}
                  y={bw.topY}
                  width={bw.width}
                  height={bw.height}
                  rx={6}
                  fill={bw.isShadow ? 'url(#purpleHatch)' : 'url(#amberHatch)'}
                  stroke={bw.isShadow ? '#9333ea' : '#f59e0b'}
                  strokeWidth="1.5"
                  strokeDasharray={bw.isShadow ? '4,2' : undefined}
                />
                {/* Block Label Badge */}
                {bw.width > 45 && (
                  <rect
                    x={bw.startX + 6}
                    y={bw.topY + 6}
                    width={Math.min(bw.width - 12, 110)}
                    height={18}
                    rx={4}
                    fill={bw.isShadow ? '#9333ea' : '#d97706'}
                  />
                )}
                {bw.width > 45 && (
                  <text
                    x={bw.startX + 12}
                    y={bw.topY + 19}
                    fill="#ffffff"
                    fontSize="9"
                    fontWeight="bold"
                  >
                    {bw.isShadow ? '⚡ SHADOW' : '🚧 BLOCK'} {bw.durationMin}m
                  </text>
                )}
              </g>
            ))}

            {/* ========================================================================= */}
            {/* LAYER 2: CONTINUOUS CORRIDOR TRAIN RAIL FLOW LINES (STRING CHARTS)        */}
            {/* ========================================================================= */}
            {filteredTrainPaths.map((p) => {
              const isHovered = hoveredTrainNumber === p.trainNumber;
              const isSelected = selectedTrain?.trainNumber === p.trainNumber;
              const hasActiveHover = hoveredTrainNumber !== null;
              const strokeOpacity = hasActiveHover ? (isHovered ? 1 : 0.2) : 0.85;

              // Build SVG Path Data: M x0 y0 L x1 y1 L ...
              const pathD = p.points
                .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`)
                .join(' ');

              // Stroke Styling
              let strokeColor = p.direction === 'DN' ? '#0284c7' : '#6366f1';
              let strokeWidth = 2.5;

              if (p.isDelayed) {
                strokeColor = '#e11d48';
                strokeWidth = 3.5;
              }
              if (p.trainType.toLowerCase().includes('freight')) {
                strokeColor = '#059669';
                strokeWidth = 2;
              }
              if (isHovered || isSelected) {
                strokeWidth = 5;
              }

              // Label placement: mid-point of string
              const midIdx = Math.floor(p.points.length / 2);
              const midPt = p.points[midIdx] || p.points[0];

              return (
                <g
                  key={`string-path-${p.trainNumber}`}
                  className="cursor-pointer transition-opacity duration-150"
                  opacity={strokeOpacity}
                  onMouseEnter={(e) => {
                    setHoveredTrainNumber(p.trainNumber);
                    setHoverItem({
                      type: 'train',
                      data: p,
                      x: e.clientX,
                      y: e.clientY,
                    });
                  }}
                  onMouseLeave={() => {
                    setHoveredTrainNumber(null);
                    setHoverItem(null);
                  }}
                  onClick={() => setSelectedTrain(p)}
                >
                  {/* Invisible thick hover hit-box */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="16"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  {/* Glow outline when hovered or selected */}
                  {(isHovered || isSelected) && (
                    <path
                      d={pathD}
                      fill="none"
                      stroke={p.isDelayed ? '#fda4af' : '#93c5fd'}
                      strokeWidth="9"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      opacity="0.6"
                    />
                  )}

                  {/* Continuous Flow Trajectory Line */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    strokeDasharray={p.trainType.toLowerCase().includes('freight') ? '6,3' : undefined}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    filter="url(#stringShadow)"
                  />

                  {/* Station waypoint dots */}
                  {p.points.map((pt, pIdx) => (
                    <circle
                      key={`pt-${p.trainNumber}-${pIdx}`}
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? 4 : 2.5}
                      fill={strokeColor}
                      stroke="#ffffff"
                      strokeWidth="1"
                    />
                  ))}

                  {/* Train Number Pill Label at Mid-point */}
                  {midPt && (
                    <g transform={`translate(${midPt.x - 20}, ${midPt.y - 10})`}>
                      <rect
                        width="40"
                        height="16"
                        rx="8"
                        fill={p.isDelayed ? '#e11d48' : '#0f172a'}
                        stroke="#ffffff"
                        strokeWidth="1"
                      />
                      <text
                        x="20"
                        y="11.5"
                        fill="#ffffff"
                        fontSize="9"
                        fontWeight="bold"
                        textAnchor="middle"
                      >
                        {p.trainNumber}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        ) : (
          /* ========================================================================= */
          /* MODE 2: STREAMLINED SECTION TRACK LANES (SECTION GANTT)                   */
          /* ========================================================================= */
          <svg
            width={TOTAL_STRING_WIDTH}
            height={STRING_HEADER_HEIGHT + sections.length * 50 + 30}
            className="select-none font-sans bg-white"
          >
            {/* Header */}
            <rect x={0} y={0} width={TOTAL_STRING_WIDTH} height={STRING_HEADER_HEIGHT} fill="#f8fafc" />
            <line x1={0} y1={STRING_HEADER_HEIGHT} x2={TOTAL_STRING_WIDTH} y2={STRING_HEADER_HEIGHT} stroke="#e2e8f0" strokeWidth="1.5" />
            <text x={16} y={24} fill="#475569" fontSize="11" fontWeight="bold">
              BLOCK SECTION LANES ({sections.length})
            </text>

            {hourTicks.map((hour) => {
              const x = STATION_COL_WIDTH + minToX(hour * 60);
              return (
                <g key={`lane-ruler-${hour}`}>
                  <line x1={x} y1={STRING_HEADER_HEIGHT} x2={x} y2={STRING_HEADER_HEIGHT + sections.length * 50} stroke="#f1f5f9" strokeWidth="1" />
                  <text x={x} y={24} fill="#64748b" fontSize="10" textAnchor="middle">
                    {String(hour).padStart(2, '0')}:00
                  </text>
                </g>
              );
            })}

            {sections.map((sec, idx) => {
              const y = STRING_HEADER_HEIGHT + idx * 50;
              const isUp = sec.section_code.includes('UP');
              const secTrains = trains.filter((t) => t.block_section_id === sec.id);
              const secBlocks = blocks.filter(
                (b) => b.block_section_id === sec.id && (!b.planned_start || b.planned_start.startsWith(selectedDate))
              );

              return (
                <g key={`lane-${sec.id}`}>
                  {/* Row background */}
                  <rect x={0} y={y} width={TOTAL_STRING_WIDTH} height={50} fill={idx % 2 === 0 ? '#ffffff' : '#fafafa'} />
                  <line x1={0} y1={y + 50} x2={TOTAL_STRING_WIDTH} y2={y + 50} stroke="#f1f5f9" strokeWidth="1" />

                  {/* Section Label */}
                  <rect x={0} y={y} width={STATION_COL_WIDTH} height={50} fill="#ffffff" />
                  <line x1={STATION_COL_WIDTH} y1={y} x2={STATION_COL_WIDTH} y2={y + 50} stroke="#e2e8f0" strokeWidth="1" />

                  <rect
                    x={12}
                    y={y + 14}
                    width={26}
                    height={20}
                    rx={5}
                    fill={isUp ? '#eff6ff' : '#f0fdf4'}
                    stroke={isUp ? '#93c5fd' : '#86efac'}
                  />
                  <text x={25} y={y + 28} fill={isUp ? '#1d4ed8' : '#15803d'} fontSize="9.5" fontWeight="bold" textAnchor="middle">
                    {isUp ? 'UP' : 'DN'}
                  </text>
                  <text x={44} y={y + 24} fill="#0f172a" fontSize="11" fontWeight="bold">
                    {sec.section_code}
                  </text>
                  <text x={44} y={y + 38} fill="#64748b" fontSize="9">
                    {sec.from_station_code} → {sec.to_station_code} • {sec.length_km || 0} km
                  </text>

                  {/* Track Rail Line */}
                  <line x1={STATION_COL_WIDTH} y1={y + 25} x2={TOTAL_STRING_WIDTH} y2={y + 25} stroke="#cbd5e1" strokeWidth="2" />

                  {/* Sleek Aerodynamic Train Flow Capsules */}
                  {secTrains.map((t) => {
                    const startMin = toMinutes(t.forecast_entry || t.scheduled_entry);
                    const endMin = toMinutes(t.forecast_exit || t.scheduled_exit);
                    const tx = STATION_COL_WIDTH + minToX(startMin);
                    const tw = Math.max(24, minToX(endMin) - minToX(startMin));
                    const isDelayed = t.delay_minutes > 0;

                    return (
                      <g
                        key={`lane-train-${t.id}`}
                        className="cursor-pointer hover:opacity-90"
                        onMouseEnter={(e) =>
                          setHoverItem({
                            type: 'train',
                            data: { trainNumber: t.train_number, trainName: t.train_name, maxDelay: t.delay_minutes, isDelayed, direction: isUp ? 'UP' : 'DN' },
                            x: e.clientX,
                            y: e.clientY,
                          })
                        }
                        onMouseLeave={() => setHoverItem(null)}
                      >
                        {/* Streamlined Train Capsule */}
                        <rect
                          x={tx}
                          y={y + 12}
                          width={tw}
                          height={26}
                          rx={13}
                          fill={isDelayed ? '#e11d48' : '#0284c7'}
                          stroke="#ffffff"
                          strokeWidth="1.5"
                          filter="url(#stringShadow)"
                        />
                        {/* Train Number */}
                        {tw > 36 && (
                          <text x={tx + tw / 2} y={y + 28} fill="#ffffff" fontSize="9.5" fontWeight="bold" textAnchor="middle">
                            {isUp ? '◀ ' : ''}#{t.train_number}{!isUp ? ' ▶' : ''}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* Maintenance Blocks */}
                  {secBlocks.map((b) => {
                    const startMin = toMinutes(b.planned_start);
                    const endMin = toMinutes(b.planned_end);
                    const bx = STATION_COL_WIDTH + minToX(startMin);
                    const bw = Math.max(16, minToX(endMin) - minToX(startMin));
                    const isShadow = b.block_type === 'shadow';

                    return (
                      <g
                        key={`lane-blk-${b.id}`}
                        className="cursor-pointer"
                        onMouseEnter={(e) =>
                          setHoverItem({
                            type: isShadow ? 'shadow_block' : 'primary_block',
                            data: b,
                            x: e.clientX,
                            y: e.clientY,
                          })
                        }
                        onMouseLeave={() => setHoverItem(null)}
                      >
                        <rect
                          x={bx}
                          y={y + 8}
                          width={bw}
                          height={34}
                          rx={6}
                          fill={isShadow ? 'url(#purpleHatch)' : 'url(#amberHatch)'}
                          stroke={isShadow ? '#9333ea' : '#f59e0b'}
                          strokeWidth="1.5"
                        />
                      </g>
                    );
                  })}
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {/* 4. Interactive Train Floating Hover Tooltip */}
      {hoverItem && (
        <div
          className="fixed z-50 pointer-events-none bg-white border border-slate-300 text-slate-800 rounded-xl p-3 shadow-xl text-xs max-w-sm"
          style={{
            left: `${hoverItem.x + 14}px`,
            top: `${hoverItem.y + 14}px`,
          }}
        >
          {hoverItem.type === 'train' && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
                <span className="font-extrabold text-slate-900 flex items-center gap-1.5">
                  <Train className="w-4 h-4 text-indigo-600" />
                  Train #{hoverItem.data.trainNumber}
                </span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    hoverItem.data.isDelayed
                      ? 'bg-rose-50 text-rose-700 border border-rose-200'
                      : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  }`}
                >
                  {hoverItem.data.isDelayed ? `+${hoverItem.data.maxDelay}m Delay` : 'On Time'}
                </span>
              </div>
              <p className="text-xs text-slate-600 font-medium">{hoverItem.data.trainName}</p>
              <div className="grid grid-cols-2 gap-2 text-[11px] pt-1">
                <div>
                  <span className="text-slate-400">Direction:</span>{' '}
                  <strong className="text-slate-700">
                    {hoverItem.data.direction === 'DN' ? 'Down (to BZA)' : 'Up (to VSKP)'}
                  </strong>
                </div>
                {hoverItem.data.originStation && (
                  <div>
                    <span className="text-slate-400">Route:</span>{' '}
                    <strong className="text-slate-700">
                      {hoverItem.data.originStation} → {hoverItem.data.destStation}
                    </strong>
                  </div>
                )}
              </div>
              <p className="text-[10px] text-indigo-600 font-semibold pt-1 border-t border-slate-100">
                Click trajectory string to open detailed train timetable inspector
              </p>
            </div>
          )}

          {(hoverItem.type === 'primary_block' || hoverItem.type === 'shadow_block') && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between border-b border-slate-100 pb-1">
                <span className="font-bold text-amber-700 flex items-center gap-1">
                  <ShieldCheck className="w-4 h-4 text-amber-600" />
                  {hoverItem.type === 'shadow_block' ? 'Shadow Block Piggyback' : 'Primary Track Possession'}
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                  {hoverItem.data.source_system || 'ENGINEERING'}
                </span>
              </div>
              <p className="text-xs text-slate-700 font-medium">
                Section: <strong>{hoverItem.data.section_code}</strong>
              </p>
              <p className="text-xs text-slate-600">
                Work: {hoverItem.data.defect_type || hoverItem.data.defect_code || 'Maintenance Possession'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* 5. Interactive Train Itinerary Inspector Drawer */}
      {selectedTrain && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 backdrop-blur-xs flex justify-end">
          <div className="bg-white w-full max-w-md h-full shadow-2xl p-6 flex flex-col justify-between overflow-y-auto border-l border-slate-200">
            <div>
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-indigo-50 text-indigo-700 rounded-xl border border-indigo-100">
                    <Train className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-extrabold text-slate-900">
                      Train #{selectedTrain.trainNumber}
                    </h3>
                    <p className="text-xs text-slate-500">{selectedTrain.trainName}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedTrain(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Status Header Pill */}
              <div className="mt-4 p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <span className="text-[11px] text-slate-500 font-medium">Corridor Direction</span>
                  <p className="text-xs font-bold text-slate-800">
                    {selectedTrain.direction === 'DN' ? 'Down Line (VSKP → BZA)' : 'Up Line (BZA → VSKP)'}
                  </p>
                </div>
                <div>
                  <span className="text-[11px] text-slate-500 font-medium">Schedule Delay</span>
                  <p className={`text-xs font-extrabold ${selectedTrain.isDelayed ? 'text-rose-600' : 'text-emerald-600'}`}>
                    {selectedTrain.isDelayed ? `+${selectedTrain.maxDelay} min delay` : 'Running On-Time'}
                  </p>
                </div>
              </div>

              {/* Station Waypoint Progression */}
              <div className="mt-5">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
                  Corridor Progression ({selectedTrain.movements.length} Sections)
                </h4>
                <div className="space-y-2">
                  {selectedTrain.movements.map((m, idx) => (
                    <div
                      key={`mov-${m.id || idx}`}
                      className="p-2.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="w-5 h-5 rounded-full bg-indigo-50 text-indigo-700 font-bold flex items-center justify-center text-[10px]">
                            {idx + 1}
                          </span>
                          <strong className="text-slate-800">{m.section_code}</strong>
                        </div>
                        <span className="text-[10px] text-slate-400 mt-0.5 ml-6.5 block">
                          Forecast: {formatMins(toMinutes(m.forecast_entry))} → {formatMins(toMinutes(m.forecast_exit))}
                        </span>
                      </div>
                      <div className="text-right">
                        {m.delay_minutes > 0 ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                            +{m.delay_minutes}m
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            On-Time
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={() => setSelectedTrain(null)}
              className="mt-6 w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl shadow-sm transition"
            >
              Close Inspector
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
