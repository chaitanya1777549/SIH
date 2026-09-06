import React, { useState, useMemo } from 'react';
import { Station, BlockSection, TrainMovement, CorridorBlock } from '../../types';
import { Clock, Play, Pause, RotateCcw, Train, Info } from 'lucide-react';

interface CorridorTrackMapProps {
  stations: Station[];
  sections: BlockSection[];
  trains: TrainMovement[];
  blocks: CorridorBlock[];
  selectedDate: string;
}

export const CorridorTrackMap: React.FC<CorridorTrackMapProps> = ({
  stations,
  sections,
  trains,
  blocks,
  selectedDate,
}) => {
  // Scrubber time in minutes from midnight (0 - 1439)
  const [timeMin, setTimeMin] = useState<number>(600); // default 10:00 AM
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [hoveredSection, setHoveredSection] = useState<BlockSection | null>(null);

  // Play / Animation effect
  React.useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        setTimeMin((prev) => (prev >= 1435 ? 0 : prev + 5));
      }, 500);
    }
    return () => clearInterval(interval);
  }, [isPlaying]);

  // Convert minutes to HH:MM format
  const formatTime = (mins: number) => {
    const h = String(Math.floor(mins / 60)).padStart(2, '0');
    const m = String(mins % 60).padStart(2, '0');
    return `${h}:${m}`;
  };

  // Convert an ISO timestamp to minutes of day
  const toMinutesOfDay = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.getHours() * 60 + d.getMinutes();
    } catch {
      return 0;
    }
  };

  // Determine active blocks at current scrubber time
  const activeBlocksBySection = useMemo(() => {
    const map = new Map<string, CorridorBlock[]>();
    blocks.forEach((b) => {
      const startMin = toMinutesOfDay(b.planned_start);
      const endMin = toMinutesOfDay(b.planned_end);
      if (timeMin >= startMin && timeMin <= endMin) {
        const list = map.get(b.block_section_id) || [];
        list.push(b);
        map.set(b.block_section_id, list);
      }
    });
    return map;
  }, [blocks, timeMin]);

  // Determine trains on corridor at current scrubber time
  const activeTrainsBySection = useMemo(() => {
    const map = new Map<string, TrainMovement[]>();
    trains.forEach((t) => {
      const entryMin = toMinutesOfDay(t.forecast_entry || t.scheduled_entry);
      const exitMin = toMinutesOfDay(t.forecast_exit || t.scheduled_exit);
      if (timeMin >= entryMin && timeMin <= exitMin) {
        const list = map.get(t.block_section_id) || [];
        list.push(t);
        map.set(t.block_section_id, list);
      }
    });
    return map;
  }, [trains, timeMin]);

  // Sort stations geographically VSKP -> BZA
  const sortedStations = useMemo(() => {
    return [...stations].sort((a, b) => a.sequence_on_corridor - b.sequence_on_corridor);
  }, [stations]);

  // Group sections by station pair to show UP and DN lines
  const stationPairs = useMemo(() => {
    const pairs: {
      from: Station;
      to: Station;
      upSection?: BlockSection;
      dnSection?: BlockSection;
    }[] = [];

    for (let i = 0; i < sortedStations.length - 1; i++) {
      const fromStn = sortedStations[i];
      const toStn = sortedStations[i + 1];

      const dnSec = sections.find(
        (s) =>
          (s.from_station_code === fromStn.station_code && s.to_station_code === toStn.station_code) ||
          s.section_code.startsWith(`${fromStn.station_code}-${toStn.station_code}-DN`)
      );

      const upSec = sections.find(
        (s) =>
          (s.from_station_code === toStn.station_code && s.to_station_code === fromStn.station_code) ||
          s.section_code.startsWith(`${toStn.station_code}-${fromStn.station_code}-UP`)
      );

      pairs.push({ from: fromStn, to: toStn, upSection: upSec, dnSection: dnSec });
    }
    return pairs;
  }, [sortedStations, sections]);

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-5 space-y-5 shadow-sm text-slate-800">
      {/* Top Map Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="bg-sky-50 text-sky-700 p-2.5 rounded-xl border border-sky-100">
              <Train className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-slate-900 flex items-center gap-2">
                Corridor Track Possession & Movement Map
                <span className="text-[11px] bg-slate-100 text-slate-700 px-2.5 py-0.5 rounded-full font-semibold border border-slate-200">
                  350 km • 12 Stations • 22 Sections
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Visual status of UP & DOWN main lines on <strong className="text-slate-800">{selectedDate}</strong>
              </p>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-xs bg-slate-50 px-3.5 py-2 rounded-xl border border-slate-200">
          <div className="flex items-center gap-1.5 text-slate-700 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span>Clear</span>
          </div>
          <div className="flex items-center gap-1.5 text-amber-800 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <span>Primary Block</span>
          </div>
          <div className="flex items-center gap-1.5 text-purple-800 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500" />
            <span>Shadow Block</span>
          </div>
          <div className="flex items-center gap-1.5 text-rose-700 font-bold">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
            <span>Emergency Possession</span>
          </div>
        </div>
      </div>

      {/* 24-Hour Time Scrubber */}
      <div className="bg-slate-50 border border-slate-200/90 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition ${
                isPlaying ? 'bg-amber-600 text-white shadow-xs' : 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-xs'
              }`}
            >
              {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              <span>{isPlaying ? 'Pause' : 'Play Timeline'}</span>
            </button>
            <button
              onClick={() => setTimeMin(0)}
              className="p-2 rounded-xl text-xs bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 shadow-2xs transition"
              title="Reset to 00:00"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <div className="bg-white px-3 py-1 rounded-xl border border-slate-300 shadow-2xs font-mono font-extrabold text-sm text-slate-900 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-indigo-600" />
              <span>{formatTime(timeMin)}</span>
              <span className="text-[10px] text-slate-400 font-sans font-normal">HRS</span>
            </div>
          </div>

          {/* Quick presets */}
          <div className="flex items-center gap-1 text-xs">
            <span className="text-slate-500 text-[11px] font-medium mr-1 hidden sm:inline">Presets:</span>
            {[
              { label: '06:00', val: 360 },
              { label: '10:00', val: 600 },
              { label: '14:00', val: 840 },
              { label: '18:00', val: 1080 },
              { label: '22:00', val: 1320 },
            ].map((p) => (
              <button
                key={p.label}
                onClick={() => setTimeMin(p.val)}
                className="px-2.5 py-1 rounded-lg bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 border border-slate-200 text-[11px] font-bold transition"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Range Slider */}
        <div className="relative pt-1">
          <input
            type="range"
            min={0}
            max={1439}
            step={5}
            value={timeMin}
            onChange={(e) => setTimeMin(Number(e.target.value))}
            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
          />
          <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1 font-semibold">
            <span>00:00</span>
            <span>04:00</span>
            <span>08:00</span>
            <span>12:00</span>
            <span>16:00</span>
            <span>20:00</span>
            <span>24:00</span>
          </div>
        </div>
      </div>

      {/* Schematic Track Diagram - High Contrast Dark Radar Canvas */}
      <div className="overflow-x-auto pb-2">
        <div className="min-w-[1000px] bg-slate-950 border border-slate-800 rounded-2xl p-6 relative space-y-12 shadow-md">
          {/* Corridor Direction Indicators */}
          <div className="flex justify-between text-[11px] font-mono text-slate-400 border-b border-slate-800 pb-2.5">
            <span className="flex items-center gap-1.5 text-emerald-400 font-bold">
              <span>➔</span> DOWN Line (VSKP to BZA)
            </span>
            <span className="flex items-center gap-1.5 text-sky-400 font-bold">
              UP Line (BZA to VSKP) <span>➔</span>
            </span>
          </div>

          {/* Track Lines with Nodes */}
          <div className="relative pt-6 pb-6">
            {/* DOWN TRACK LINE */}
            <div className="absolute top-[38px] left-8 right-8 h-1.5 bg-slate-800 rounded" />
            {/* UP TRACK LINE */}
            <div className="absolute top-[88px] left-8 right-8 h-1.5 bg-slate-800 rounded" />

            {/* Grid of Station Nodes */}
            <div className="flex justify-between items-start relative z-10 px-2">
              {sortedStations.map((stn, idx) => (
                <div key={stn.id} className="flex flex-col items-center group relative">
                  {/* Station Code Badge */}
                  <div className="w-10 h-10 rounded-xl bg-slate-900 border-2 border-slate-700 group-hover:border-indigo-400 text-white flex items-center justify-center font-mono font-extrabold text-xs shadow-lg transition-all duration-150">
                    {stn.station_code}
                  </div>

                  {/* Station Name & KM */}
                  <div className="text-center mt-2">
                    <span className="text-[11px] font-bold text-slate-200 block truncate max-w-[85px]">
                      {stn.station_name}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      km {stn.distance_from_origin_km || idx * 30}
                    </span>
                  </div>

                  {/* DOWN Track Point */}
                  <div className="absolute top-[28px] w-3.5 h-3.5 rounded-full bg-slate-700 border-2 border-slate-900 group-hover:bg-emerald-400 transition" />
                  {/* UP Track Point */}
                  <div className="absolute top-[78px] w-3.5 h-3.5 rounded-full bg-slate-700 border-2 border-slate-900 group-hover:bg-sky-400 transition" />
                </div>
              ))}
            </div>

            {/* Block Section Segments (Overlaid on tracks) */}
            <div className="relative mt-8 space-y-4">
              {/* DOWN Line Section Overlays */}
              <div className="flex justify-between px-8">
                {stationPairs.map((pair, idx) => {
                  const sec = pair.dnSection;
                  if (!sec) return <div key={idx} className="flex-1" />;

                  const activeBlks = activeBlocksBySection.get(sec.id) || [];
                  const activeTrns = activeTrainsBySection.get(sec.id) || [];
                  const isBlocked = activeBlks.length > 0;
                  const hasEmergency = activeBlks.some((b) => b.is_emergency || b.status === 'emergency');
                  const hasShadow = activeBlks.some((b) => b.block_type === 'shadow');

                  let segmentColor = 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300';
                  if (hasEmergency) {
                    segmentColor = 'bg-rose-600/30 border-rose-500 text-rose-300 animate-pulse';
                  } else if (hasShadow) {
                    segmentColor = 'bg-purple-600/30 border-purple-500 text-purple-300';
                  } else if (isBlocked) {
                    segmentColor = 'bg-amber-600/30 border-amber-500 text-amber-300';
                  }

                  return (
                    <div
                      key={sec.id}
                      onMouseEnter={() => setHoveredSection(sec)}
                      onMouseLeave={() => setHoveredSection(null)}
                      className={`flex-1 mx-1.5 p-2 rounded-xl border text-center transition-all duration-200 cursor-pointer ${segmentColor} hover:scale-105 hover:z-20`}
                    >
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="font-bold">{sec.section_code}</span>
                        {isBlocked && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-black/40 font-bold">
                            {hasEmergency ? 'EMERGENCY' : hasShadow ? 'SHADOW' : 'BLOCKED'}
                          </span>
                        )}
                      </div>

                      {/* Moving Trains on Section */}
                      {activeTrns.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1 justify-center">
                          {activeTrns.map((t) => (
                            <span
                              key={t.id}
                              className="inline-flex items-center gap-0.5 bg-sky-500 text-white px-1.5 py-0.5 rounded text-[9px] font-mono font-bold shadow"
                              title={`${t.train_number} - ${t.train_name || ''} (Delay: ${t.delay_minutes}m)`}
                            >
                              🚆 {t.train_number}
                              {t.delay_minutes > 0 && <span className="text-amber-200">+{t.delay_minutes}m</span>}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* UP Line Section Overlays */}
              <div className="flex justify-between px-8">
                {stationPairs.map((pair, idx) => {
                  const sec = pair.upSection;
                  if (!sec) return <div key={idx} className="flex-1" />;

                  const activeBlks = activeBlocksBySection.get(sec.id) || [];
                  const activeTrns = activeTrainsBySection.get(sec.id) || [];
                  const isBlocked = activeBlks.length > 0;
                  const hasEmergency = activeBlks.some((b) => b.is_emergency || b.status === 'emergency');
                  const hasShadow = activeBlks.some((b) => b.block_type === 'shadow');

                  let segmentColor = 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300';
                  if (hasEmergency) {
                    segmentColor = 'bg-rose-600/30 border-rose-500 text-rose-300 animate-pulse';
                  } else if (hasShadow) {
                    segmentColor = 'bg-purple-600/30 border-purple-500 text-purple-300';
                  } else if (isBlocked) {
                    segmentColor = 'bg-amber-600/30 border-amber-500 text-amber-300';
                  }

                  return (
                    <div
                      key={sec.id}
                      onMouseEnter={() => setHoveredSection(sec)}
                      onMouseLeave={() => setHoveredSection(null)}
                      className={`flex-1 mx-1.5 p-2 rounded-xl border text-center transition-all duration-200 cursor-pointer ${segmentColor} hover:scale-105 hover:z-20`}
                    >
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="font-bold">{sec.section_code}</span>
                        {isBlocked && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-black/40 font-bold">
                            {hasEmergency ? 'EMERGENCY' : hasShadow ? 'SHADOW' : 'BLOCKED'}
                          </span>
                        )}
                      </div>

                      {/* Moving Trains on Section */}
                      {activeTrns.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1 justify-center">
                          {activeTrns.map((t) => (
                            <span
                              key={t.id}
                              className="inline-flex items-center gap-0.5 bg-indigo-500 text-white px-1.5 py-0.5 rounded text-[9px] font-mono font-bold shadow"
                              title={`${t.train_number} - ${t.train_name || ''} (Delay: ${t.delay_minutes}m)`}
                            >
                              🚆 {t.train_number}
                              {t.delay_minutes > 0 && <span className="text-amber-200">+{t.delay_minutes}m</span>}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Section Hover Inspector Card */}
          {hoveredSection && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 text-xs space-y-2 shadow-2xl animate-in fade-in duration-150 text-white">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="font-bold text-white font-mono text-sm flex items-center gap-2">
                  <Info className="w-4 h-4 text-sky-400" />
                  Section: {hoveredSection.section_code}
                </span>
                <span className="text-slate-400 font-mono">
                  {hoveredSection.from_station_code} ➔ {hoveredSection.to_station_code} ({hoveredSection.length_km} km)
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <span className="text-slate-500 text-[10px] block font-medium">Track Code</span>
                  <span className="text-slate-200 font-mono">{hoveredSection.track_code || 'MAIN'}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block font-medium">Possession Status</span>
                  <span className="font-bold text-emerald-400">
                    {activeBlocksBySection.get(hoveredSection.id)?.length ? 'MAINTENANCE OCCUPIED' : 'CLEAR FOR TRAFFIC'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block font-medium">Active Trains at {formatTime(timeMin)}</span>
                  <span className="text-sky-400 font-bold font-mono">
                    {activeTrainsBySection.get(hoveredSection.id)?.length || 0} trains
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block font-medium">Active Blocks at {formatTime(timeMin)}</span>
                  <span className="text-amber-400 font-bold font-mono">
                    {activeBlocksBySection.get(hoveredSection.id)?.length || 0} blocks
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
