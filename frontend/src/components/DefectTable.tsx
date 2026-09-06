import React, { useState, useMemo } from 'react';
import { Defect, Severity, DefectStatus } from '../types';
import { Search, Filter, Clock, MapPin, AlertCircle, CheckCircle, ShieldAlert } from 'lucide-react';

interface DefectTableProps {
  defects: Defect[];
  department: string;
  loading: boolean;
}

export const DefectTable: React.FC<DefectTableProps> = ({ defects, department, loading }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  const filteredDefects = useMemo(() => {
    return defects.filter((d) => {
      const matchesSearch =
        d.defect_code.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.defect_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (d.section_code && d.section_code.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (d.description && d.description.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesStatus = statusFilter === 'all' || d.status === statusFilter;
      const matchesSeverity = severityFilter === 'all' || d.severity === severityFilter;

      return matchesSearch && matchesStatus && matchesSeverity;
    });
  }, [defects, searchTerm, statusFilter, severityFilter]);

  const getSeverityBadge = (sev: Severity) => {
    switch (sev) {
      case 'critical':
        return 'bg-rose-50 text-rose-700 border-rose-200 font-bold';
      case 'high':
        return 'bg-amber-50 text-amber-700 border-amber-200 font-semibold';
      case 'medium':
        return 'bg-yellow-50 text-yellow-700 border-yellow-200 font-semibold';
      case 'low':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      default:
        return 'bg-slate-100 text-slate-600 border-slate-200';
    }
  };

  const getStatusPill = (status: DefectStatus) => {
    switch (status) {
      case 'open':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
            Open
          </span>
        );
      case 'requested':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Queued
          </span>
        );
      case 'allocated':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle className="w-3 h-3" />
            Allocated
          </span>
        );
      case 'resolved':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
            Resolved
          </span>
        );
    }
  };

  const getCriticalityBarColor = (score: number) => {
    if (score >= 75) return 'from-rose-500 to-red-600 text-rose-700';
    if (score >= 50) return 'from-amber-500 to-orange-500 text-amber-700';
    if (score >= 35) return 'from-yellow-500 to-amber-500 text-yellow-700';
    return 'from-blue-500 to-indigo-500 text-blue-700';
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl shadow-sm overflow-hidden text-slate-800">
      {/* Search & Filters Toolbar */}
      <div className="p-4 border-b border-slate-100 bg-white flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder={`Search ${department} defects by code, type, section, or description...`}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white transition"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Status Filter */}
          <div className="flex items-center gap-1.5 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500 font-medium">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-800 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="all">All ({defects.length})</option>
              <option value="open">Open</option>
              <option value="allocated">Allocated</option>
              <option value="requested">Queued</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center gap-1.5 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200 text-xs">
            <span className="text-slate-500 font-medium">Severity:</span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-transparent text-slate-800 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600 uppercase tracking-wider font-bold border-b border-slate-200">
            <tr>
              <th className="py-3 px-4">Defect Code</th>
              <th className="py-3 px-4">Corridor Section</th>
              <th className="py-3 px-4">Defect Type</th>
              <th className="py-3 px-4">Severity</th>
              <th className="py-3 px-4">ML Criticality</th>
              <th className="py-3 px-4">Duration</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Work Category</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                    <span className="text-xs font-medium">Loading {department} defects from PostgreSQL...</span>
                  </div>
                </td>
              </tr>
            ) : filteredDefects.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <AlertCircle className="w-8 h-8 text-slate-300" />
                    <p className="text-xs font-semibold text-slate-600">No matching {department} defects found</p>
                    <p className="text-[11px] text-slate-400">Try adjusting your search or filters</p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredDefects.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50/80 transition-colors">
                  {/* Defect Code */}
                  <td className="py-3 px-4 font-mono font-bold text-indigo-700">
                    {d.defect_code}
                  </td>

                  {/* Section */}
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-1.5">
                      <MapPin className="w-3.5 h-3.5 text-slate-400" />
                      <span className="font-semibold text-slate-800">
                        {d.section_code || 'Corridor Link'}
                      </span>
                    </div>
                  </td>

                  {/* Type */}
                  <td className="py-3 px-4">
                    <span className="font-medium text-slate-900">{d.defect_type}</span>
                    {d.description && (
                      <p className="text-[11px] text-slate-400 truncate max-w-xs">{d.description}</p>
                    )}
                  </td>

                  {/* Severity */}
                  <td className="py-3 px-4">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] border uppercase tracking-wider ${getSeverityBadge(
                        d.severity
                      )}`}
                    >
                      {d.severity}
                    </span>
                  </td>

                  {/* ML Criticality Bar */}
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 w-20 bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200">
                        <div
                          className={`h-full bg-gradient-to-r ${getCriticalityBarColor(
                            d.criticality_score
                          )}`}
                          style={{ width: `${Math.min(100, d.criticality_score)}%` }}
                        ></div>
                      </div>
                      <span
                        className={`text-xs font-bold ${
                          d.criticality_score >= 70
                            ? 'text-rose-600'
                            : d.criticality_score >= 40
                            ? 'text-amber-600'
                            : 'text-slate-600'
                        }`}
                      >
                        {d.criticality_score}
                      </span>
                    </div>
                  </td>

                  {/* Duration */}
                  <td className="py-3 px-4 text-slate-600">
                    {d.estimated_duration_min} mins
                  </td>

                  {/* Status */}
                  <td className="py-3 px-4">{getStatusPill(d.status)}</td>

                  {/* Work Category */}
                  <td className="py-3 px-4 text-slate-500 capitalize">
                    {d.work_category ? d.work_category.replace('_', ' ') : 'Defect'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Footer info bar */}
      <div className="p-3 bg-slate-50 border-t border-slate-100 text-[11px] text-slate-500 flex items-center justify-between">
        <span>Showing {filteredDefects.length} of {defects.length} total defects</span>
        <span>ML Criticality Scored via Gradient Boosted Model (Phase C)</span>
      </div>
    </div>
  );
};
