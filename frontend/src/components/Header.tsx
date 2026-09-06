import React from 'react';
import { ActiveView } from '../types';
import { API_BASE } from '../api/client';
import { Mic, PlusCircle, Train, Zap, Radio, ShieldAlert, Layers, Database } from 'lucide-react';

interface HeaderProps {
  activeView: ActiveView;
  onSelectView: (view: ActiveView) => void;
  onOpenVoiceModal: () => void;
  onOpenManualModal: () => void;
  isOnline: boolean;
  defectCounts: { total: number; open: number; allocated: number; critical: number };
}

export const Header: React.FC<HeaderProps> = ({
  activeView,
  onSelectView,
  onOpenVoiceModal,
  onOpenManualModal,
  isOnline,
  defectCounts,
}) => {
  const navTabs: { code: ActiveView; name: string; icon: React.ReactNode; activeColor: string }[] = [
    {
      code: 'COA',
      name: 'Master Control',
      icon: <Layers className="w-4 h-4" />,
      activeColor: 'bg-indigo-600 text-white shadow-sm shadow-indigo-200',
    },
    {
      code: 'TMS',
      name: 'Track (Civil)',
      icon: <Train className="w-4 h-4" />,
      activeColor: 'bg-amber-600 text-white shadow-sm shadow-amber-200',
    },
    {
      code: 'SMMS',
      name: 'Signal & Telecom',
      icon: <Radio className="w-4 h-4" />,
      activeColor: 'bg-emerald-600 text-white shadow-sm shadow-emerald-200',
    },
    {
      code: 'TDMS',
      name: 'Traction (OHE)',
      icon: <Zap className="w-4 h-4" />,
      activeColor: 'bg-blue-600 text-white shadow-sm shadow-blue-200',
    },
  ];

  return (
    <header className="border-b border-slate-200/80 bg-white/95 backdrop-blur-md sticky top-0 z-40 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          {/* Left: Branding & Status */}
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-br from-indigo-600 to-blue-700 p-2.5 rounded-xl text-white shadow-sm">
              <Train className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-extrabold text-slate-900 tracking-tight">
                  SIH26027 Rail Block Planner
                </h1>
                <span
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                    isOnline
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200'
                  }`}
                  title={`API Target: ${API_BASE || 'Local Vite Proxy'}`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isOnline ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                    }`}
                  ></span>
                  {isOnline ? 'Live Connected' : 'Offline'}
                </span>
                <span className="text-[10px] text-slate-400 font-mono hidden lg:inline">
                  • {API_BASE ? 'Render Cloud' : 'Local'}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">
                Visakhapatnam (VSKP) — Vijayawada (BZA) Corridor • 350 km • 22 Block Sections
              </p>
            </div>
          </div>

          {/* Middle: Clean Master Navigation Switcher */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200/80">
            {navTabs.map((d) => {
              const active = activeView === d.code;
              return (
                <button
                  key={d.code}
                  onClick={() => onSelectView(d.code)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all duration-150 ${
                    active
                      ? d.activeColor
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                  }`}
                >
                  {d.icon}
                  <span>{d.code}</span>
                  <span className="text-[10px] font-normal opacity-80 hidden lg:inline">({d.name})</span>
                </button>
              );
            })}
          </div>

          {/* Right: Clean Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={onOpenVoiceModal}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 shadow-sm shadow-rose-200 transition active:scale-95"
            >
              <Mic className="w-3.5 h-3.5" />
              <span>Voice Intake</span>
            </button>

            <button
              onClick={onOpenManualModal}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 shadow-xs transition"
            >
              <PlusCircle className="w-3.5 h-3.5 text-indigo-600" />
              <span>Report Issue</span>
            </button>
          </div>
        </div>

        {/* Sub-bar: Clean Metric Counters */}
        <div className="mt-2.5 pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2">
          <div className="flex items-center gap-3">
            <span>
              Active: <strong className="text-slate-900 font-semibold">{activeView === 'COA' ? 'Central Controller' : activeView}</strong>
            </span>
            <span className="text-slate-300">•</span>
            <span>
              Defects: <strong className="text-slate-900 font-semibold">{defectCounts.total}</strong>
            </span>
            <span className="text-slate-300">•</span>
            <span>
              Pending: <strong className="text-amber-700 font-bold">{defectCounts.open}</strong>
            </span>
            <span className="text-slate-300">•</span>
            <span>
              Allocated: <strong className="text-emerald-700 font-bold">{defectCounts.allocated}</strong>
            </span>
            {defectCounts.critical > 0 && (
              <>
                <span className="text-slate-300">•</span>
                <span className="inline-flex items-center gap-1 text-rose-700 font-bold bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
                  <ShieldAlert className="w-3 h-3" />
                  {defectCounts.critical} Critical
                </span>
              </>
            )}
          </div>

          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            <span className="flex items-center gap-1">
              <Database className="w-3 h-3 text-slate-400" /> Supabase PostgreSQL
            </span>
            <span className="text-slate-300">•</span>
            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 hover:text-indigo-800 font-medium hover:underline"
            >
              API Docs (/docs)
            </a>
          </div>
        </div>
      </div>
    </header>
  );
};
