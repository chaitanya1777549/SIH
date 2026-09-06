import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Department, Defect, BlockSection, DepartmentNotification, ActiveView } from './types';
import {
  getDepartmentDefects,
  getDepartmentNotifications,
  getCorridorSections,
  checkBackendHealth,
  API_BASE,
} from './api/client';
import { Header } from './components/Header';
import { NotificationStream } from './components/NotificationStream';
import { DefectTable } from './components/DefectTable';
import { VoiceIntakeModal } from './components/VoiceIntakeModal';
import { ManualReportModal } from './components/ManualReportModal';
import { CoaDashboard } from './components/coa/CoaDashboard';
import { RefreshCw, Train, Radio, Zap } from 'lucide-react';

export const App: React.FC = () => {
  const [activeView, setActiveView] = useState<ActiveView>('COA');
  const [department, setDepartment] = useState<Department>('TMS');
  const [defects, setDefects] = useState<Defect[]>([]);
  const [sections, setSections] = useState<BlockSection[]>([]);
  const [notifications, setNotifications] = useState<DepartmentNotification[]>([]);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState<boolean>(false);
  const [isManualModalOpen, setIsManualModalOpen] = useState<boolean>(false);
  const [targetEmergencyIncidentId, setTargetEmergencyIncidentId] = useState<string | null>(null);

  // 1. Load corridor block sections on mount
  useEffect(() => {
    getCorridorSections()
      .then((data) => setSections(data))
      .catch((err) => console.error('Failed to load corridor sections:', err));
  }, []);

  // 2. Load defects & notifications for selected department
  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setFetchError(null);
    try {
      const [defectList, notifList, health] = await Promise.all([
        getDepartmentDefects(department),
        getDepartmentNotifications(department),
        checkBackendHealth(),
      ]);

      setDefects(defectList);
      setNotifications(notifList);
      setIsOnline(health.status === 'healthy' || health.status === 'online');
    } catch (err: any) {
      console.error('Data loading error:', err);
      setFetchError(err?.message || String(err));
      setIsOnline(false);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [department]);

  useEffect(() => {
    loadData(true);

    // Auto-refresh every 12 seconds to stream COA decisions
    const interval = setInterval(() => {
      loadData(false);
    }, 12000);

    return () => clearInterval(interval);
  }, [department, loadData]);

  // Metric counts
  const counts = useMemo(() => {
    return {
      total: defects.length,
      open: defects.filter((d) => d.status === 'open' || d.status === 'requested').length,
      allocated: defects.filter((d) => d.status === 'allocated').length,
      critical: defects.filter((d) => d.severity === 'critical').length,
    };
  }, [defects]);

  const departmentMeta = {
    TMS: {
      title: 'Track Management System (Civil / Permanent Way)',
      subtitle: 'Oversees rails, sleepers, ballast cushions, thermit welds, ultrasonic flaw detection, and tamping cycles.',
      icon: <Train className="w-5 h-5 text-amber-600" />,
      themeBorder: 'border-amber-200',
      themeBg: 'bg-amber-50/70',
      badgeBg: 'bg-amber-100 text-amber-800 border-amber-200',
    },
    SMMS: {
      title: 'Signal Maintenance Management System (S&T)',
      subtitle: 'Oversees point machines, color-light signals, track circuits, electronic interlocking, and level crossing gates.',
      icon: <Radio className="w-5 h-5 text-emerald-600" />,
      themeBorder: 'border-emerald-200',
      themeBg: 'bg-emerald-50/70',
      badgeBg: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    },
    TDMS: {
      title: 'Traction Distribution Management System (Electrical / OHE)',
      subtitle: 'Oversees 25kV overhead catenary wires, contact wire tension, pantograph clearances, section insulators, and substations.',
      icon: <Zap className="w-5 h-5 text-blue-600" />,
      themeBorder: 'border-blue-200',
      themeBg: 'bg-blue-50/70',
      badgeBg: 'bg-blue-100 text-blue-800 border-blue-200',
    },
  };

  const meta = departmentMeta[department];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* Main Application Header */}
      <Header
        activeView={activeView}
        onSelectView={(view) => {
          setActiveView(view);
          if (view !== 'COA') {
            setDepartment(view);
          }
        }}
        onOpenVoiceModal={() => setIsVoiceModalOpen(true)}
        onOpenManualModal={() => setIsManualModalOpen(true)}
        isOnline={isOnline}
        defectCounts={counts}
      />

      {/* Content Area */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 w-full">
        {!isOnline && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-3">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
              <div>
                <p className="font-bold text-xs">Backend Connection Waiting / Inactive</p>
                <p className="text-[11px] text-rose-600 mt-0.5">
                  Target API: <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-rose-200">{API_BASE || window.location.origin}</code>
                  {fetchError ? ` • Details: ${fetchError}` : ''}
                </p>
              </div>
            </div>
            <button
              onClick={() => loadData(true)}
              className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition shadow-xs flex-shrink-0"
            >
              Retry Connection
            </button>
          </div>
        )}

        {activeView === 'COA' ? (
          /* COA MASTER INTERFACE */
          <CoaDashboard targetIncidentId={targetEmergencyIncidentId} />
        ) : (
          /* DEPARTMENTAL INTERFACE (TMS, SMMS, TDMS) */
          <>
            {/* Department Banner */}
            <div className={`p-4 rounded-2xl border ${meta.themeBorder} ${meta.themeBg} bg-white flex items-center justify-between shadow-xs`}>
              <div className="flex items-center gap-3.5">
                <div className="p-2.5 rounded-xl bg-white border border-slate-200/80 shadow-xs">
                  {meta.icon}
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-900">{meta.title}</h2>
                  <p className="text-xs text-slate-600 mt-0.5">{meta.subtitle}</p>
                </div>
              </div>
              <button
                onClick={() => loadData(true)}
                className="flex items-center gap-1.5 text-xs text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200 shadow-xs transition"
                title="Refresh defect queue"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
                <span className="hidden sm:inline font-medium">Refresh</span>
              </button>
            </div>

            {/* Real-Time Notification Stream (Green/Red/Amber Approvals from COA) */}
            <NotificationStream notifications={notifications} department={department} />

            {/* Live Defect Queue Table with Search, Filter & ML Score Bars */}
            <DefectTable defects={defects} department={department} loading={loading} />
          </>
        )}
      </main>

      {/* Modals */}
      <VoiceIntakeModal
        isOpen={isVoiceModalOpen}
        onClose={() => setIsVoiceModalOpen(false)}
        department={department}
        sections={sections}
        onDefectCreated={() => loadData(true)}
      />

      <ManualReportModal
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
        department={department}
        sections={sections}
        onDefectCreated={() => loadData(true)}
        onSwitchToCoaEmergency={(incidentId) => {
          if (incidentId) setTargetEmergencyIncidentId(incidentId);
          setActiveView('COA');
          setIsManualModalOpen(false);
        }}
      />

      {/* Simple Clean Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        <p>
          SIH26027 — AI-Powered Automatic Block Planning System • Visakhapatnam to Vijayawada Corridor • 350 km • SQLAlchemy 2.0 + Supabase PostgreSQL
        </p>
      </footer>
    </div>
  );
};
