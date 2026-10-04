import React from 'react';
import {
  Sparkles,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  PieChart,
  Hash,
  ShieldAlert,
  Info,
} from 'lucide-react';

export default function DynamicInsights({ insights = [] }) {
  if (!insights || insights.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
        <Sparkles size={36} className="mx-auto mb-2 opacity-50 text-slate-400" />
        <p className="font-semibold text-sm text-slate-600">No dynamic insights available</p>
        <p className="text-xs text-slate-400 mt-1">
          Insights will appear once extraction rules and metrics are computed.
        </p>
      </div>
    );
  }

  const formatInsightValue = (val, kind) => {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') {
      if (Number.isInteger(val)) return val.toLocaleString();
      return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    if (typeof val === 'boolean') {
      return val ? 'PASSED' : 'FLAGGED';
    }
    return String(val);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-sm">
            <Sparkles size={20} />
          </div>
          <div>
            <h3 className="font-bold text-sm text-slate-900">Dynamic Document Intelligence</h3>
            <p className="text-xs text-slate-500">
              Aggregated mathematical metrics and deterministic validation flags.
            </p>
          </div>
        </div>

        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 text-blue-700">
          {insights.length} Computed Insights
        </span>
      </div>

      {/* Grid of Insight Cards */}
      <div className="uv-insights-grid">
        {insights.map((ins) => {
          const isFlag = ins.kind === 'flag';
          const isDanger = isFlag && ins.value === false;
          const isWarn = isFlag && ins.value !== true;

          return (
            <div
              key={ins.id}
              className={`uv-insight-card ${isDanger ? 'flag-danger' : isWarn ? 'flag-warn' : ''}`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="uv-insight-title">{ins.title}</span>
                  {isFlag ? (
                    isDanger ? (
                      <ShieldAlert size={16} className="text-red-600" />
                    ) : (
                      <CheckCircle2 size={16} className="text-emerald-600" />
                    )
                  ) : (
                    <TrendingUp size={16} className="text-blue-600" />
                  )}
                </div>

                <div className="uv-insight-value">
                  {formatInsightValue(ins.value, ins.kind)}
                </div>
              </div>

              {ins.description && (
                <p className="text-xs text-slate-500 mt-3 pt-2 border-t border-slate-100">
                  {ins.description}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
