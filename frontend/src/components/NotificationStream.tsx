import React from 'react';
import { DepartmentNotification } from '../types';
import { CheckCircle2, XCircle, AlertTriangle, Info, Bell, ShieldAlert } from 'lucide-react';

interface NotificationStreamProps {
  notifications: DepartmentNotification[];
  department: string;
}

export const NotificationStream: React.FC<NotificationStreamProps> = ({
  notifications,
  department,
}) => {
  if (!notifications || notifications.length === 0) {
    return (
      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 text-xs text-slate-500 flex items-center justify-between shadow-2xs">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-slate-400" />
          <span>COA Decision Feed: No new approval/rejection decisions affecting {department} yet.</span>
        </div>
        <span className="text-[11px] text-slate-400 font-medium">Live sync active</span>
      </div>
    );
  }

  const getBadge = (type: string) => {
    switch (type) {
      case 'approved':
        return {
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />,
          border: 'border-emerald-200 bg-emerald-50/60 text-emerald-900',
          tag: 'APPROVED',
          tagBg: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        };
      case 'declined':
      case 'rejected':
      case 'revoked':
        return {
          icon: <XCircle className="w-4 h-4 text-rose-600 shrink-0" />,
          border: 'border-rose-200 bg-rose-50/60 text-rose-900',
          tag: 'DECLINED / REVOKED',
          tagBg: 'bg-rose-100 text-rose-800 border-rose-300',
        };
      case 'emergency':
        return {
          icon: <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0 animate-pulse" />,
          border: 'border-rose-300 bg-rose-50 text-rose-900',
          tag: 'EMERGENCY POSSESSION',
          tagBg: 'bg-rose-600 text-white border-rose-600 font-extrabold',
        };
      case 'deferred':
        return {
          icon: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />,
          border: 'border-amber-200 bg-amber-50/60 text-amber-900',
          tag: 'DEFERRED / PENDING',
          tagBg: 'bg-amber-100 text-amber-800 border-amber-300',
        };
      default:
        return {
          icon: <Info className="w-4 h-4 text-indigo-600 shrink-0" />,
          border: 'border-indigo-200 bg-indigo-50/60 text-indigo-900',
          tag: 'COA NOTICE',
          tagBg: 'bg-indigo-100 text-indigo-800 border-indigo-300',
        };
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
          <Bell className="w-3.5 h-3.5 text-indigo-600" />
          <span>COA Decision & Approval Stream ({department})</span>
        </h3>
        <span className="text-[11px] text-slate-400">Green = Approved • Red = Declined</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {notifications.slice(0, 4).map((n, idx) => {
          const style = getBadge(n.type);
          return (
            <div
              key={n.id || idx}
              className={`p-3.5 rounded-2xl border ${style.border} flex items-start gap-3 transition duration-150 shadow-2xs`}
            >
              {style.icon}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-0.5">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${style.tagBg}`}>
                    {style.tag}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {n.timestamp ? new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Live'}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-slate-900 truncate">{n.title}</h4>
                <p className="text-[11px] text-slate-600 leading-snug mt-0.5 line-clamp-2">
                  {n.message}
                </p>
                {n.section_code && (
                  <span className="inline-block mt-1.5 text-[10px] font-mono text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                    Section: {n.section_code}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
