import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Sliders,
  Check,
  X,
  Code,
} from 'lucide-react';

export default function ValidationPanel({ validation = {} }) {
  const rules = validation.rules || [];
  const errors = validation.errors || [];
  const overallStatus = validation.status || (errors.length > 0 ? 'fail' : 'pass');

  if (rules.length === 0 && errors.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
        <ShieldCheck size={36} className="mx-auto mb-2 opacity-50 text-emerald-500" />
        <p className="font-semibold text-sm text-slate-600">No cross-field validation rules defined</p>
        <p className="text-xs text-slate-400 mt-1">
          All individual data type validations passed successfully.
        </p>
      </div>
    );
  }

  const passCount = rules.filter((r) => r.status === 'pass').length;
  const failCount = rules.filter((r) => r.status === 'fail').length;

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <div
        className={`p-4 rounded-xl border flex items-center justify-between ${
          overallStatus === 'pass'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : 'bg-red-50 border-red-200 text-red-900'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              overallStatus === 'pass' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {overallStatus === 'pass' ? <ShieldCheck size={22} /> : <ShieldAlert size={22} />}
          </div>
          <div>
            <h3 className="font-bold text-sm">
              {overallStatus === 'pass'
                ? 'All Validation Rules Passed'
                : `${failCount} Validation ${failCount === 1 ? 'Rule' : 'Rules'} Failed`}
            </h3>
            <p className="text-xs opacity-80">
              Deterministic cross-field DSL validation executed against extracted values.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-semibold">
          <span className="px-2.5 py-1 rounded bg-white/80 shadow-xs">
            {passCount} Passed
          </span>
          {failCount > 0 && (
            <span className="px-2.5 py-1 rounded bg-red-100 text-red-800 shadow-xs">
              {failCount} Failed
            </span>
          )}
        </div>
      </div>

      {/* Rules List */}
      <div className="space-y-3">
        <h4 className="font-bold text-xs uppercase tracking-wider text-slate-400">
          Evaluated Deterministic Rules ({rules.length})
        </h4>

        {rules.map((rule, idx) => {
          const isPass = rule.status === 'pass';
          return (
            <div
              key={idx}
              className={`uv-rule-row ${isPass ? 'rule-pass' : 'rule-fail'}`}
            >
              <div>
                <div className="uv-rule-name">
                  {isPass ? (
                    <CheckCircle2 size={16} className="text-emerald-600" />
                  ) : (
                    <AlertTriangle size={16} className="text-red-600" />
                  )}
                  <span>Rule: {rule.rule || rule.name || 'Validation Rule'}</span>
                </div>

                <div className="uv-rule-detail">
                  {rule.message || (isPass ? 'Constraint satisfied' : 'Constraint violated')}
                </div>

                {rule.target && (
                  <div className="text-[11px] text-slate-400 mt-1 font-mono">
                    Target: {rule.target} • Terms: {JSON.stringify(rule.terms || [])}
                  </div>
                )}
              </div>

              <div>
                <span
                  className={`px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider ${
                    isPass
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-red-100 text-red-800'
                  }`}
                >
                  {rule.status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
