import React, { useState, useEffect } from 'react';
import { GitCompare, Clock, CheckCircle2, AlertTriangle, ArrowRight, X, RefreshCw } from 'lucide-react';
import { fetchDocumentRunsV2, compareDocumentRunsV2 } from '../../services/api';

export default function RunComparisonModal({ documentId, onClose }) {
  const [runs, setRuns] = useState([]);
  const [selectedRunA, setSelectedRunA] = useState('');
  const [selectedRunB, setSelectedRunB] = useState('');
  const [comparison, setComparison] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadRuns();
  }, [documentId]);

  const loadRuns = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDocumentRunsV2(documentId);
      setRuns(data || []);
      if (data && data.length >= 2) {
        setSelectedRunA(data[1].id);
        setSelectedRunB(data[0].id);
      } else if (data && data.length === 1) {
        setSelectedRunA(data[0].id);
        setSelectedRunB(data[0].id);
      }
    } catch (err) {
      setError(err.message || 'Failed to load document runs.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCompare = async () => {
    if (!selectedRunA || !selectedRunB) return;
    setIsComparing(true);
    setError(null);
    try {
      const compData = await compareDocumentRunsV2(documentId, selectedRunA, selectedRunB);
      setComparison(compData);
    } catch (err) {
      setError(err.message || 'Comparison failed.');
    } finally {
      setIsComparing(false);
    }
  };

  useEffect(() => {
    if (selectedRunA && selectedRunB) {
      handleCompare();
    }
  }, [selectedRunA, selectedRunB]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 rounded-lg">
              <GitCompare size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-lg text-slate-100">Pipeline Run Comparison</h3>
              <p className="text-xs text-slate-400">
                Compare field values, latency, and calibrated confidence across extraction pipeline runs.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Run Selector Bar */}
        <div className="px-6 py-4 bg-slate-800/40 border-b border-slate-800 flex flex-wrap items-center gap-4 justify-between">
          <div className="flex items-center gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Baseline Run (A)
              </label>
              <select
                value={selectedRunA}
                onChange={(e) => setSelectedRunA(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-xs rounded-md px-3 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id} ({r.pipeline_version} - {r.stage})
                  </option>
                ))}
              </select>
            </div>

            <div className="pt-5 text-slate-500">
              <ArrowRight size={16} />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Candidate Run (B)
              </label>
              <select
                value={selectedRunB}
                onChange={(e) => setSelectedRunB(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-xs rounded-md px-3 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id} ({r.pipeline_version} - {r.stage})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button
            onClick={handleCompare}
            disabled={isComparing || !selectedRunA || !selectedRunB}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-md shadow-sm transition disabled:opacity-50"
          >
            <RefreshCw size={13} className={isComparing ? 'animate-spin' : ''} />
            {isComparing ? 'Comparing...' : 'Refresh Diff'}
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs rounded-lg flex items-center gap-2">
              <AlertTriangle size={15} />
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="py-12 text-center text-slate-400 text-sm">Loading run history...</div>
          ) : runs.length < 1 ? (
            <div className="py-12 text-center text-slate-400 text-sm">No extraction runs recorded for this document.</div>
          ) : comparison ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-800/60 border border-slate-700/80 rounded-lg p-4 space-y-2">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Run A (Baseline)</div>
                  <div className="text-sm font-bold text-slate-200">{comparison.run_a.id}</div>
                  <div className="text-xs text-slate-400 flex gap-4">
                    <span>Pipeline: <strong className="text-slate-300">{comparison.run_a.pipeline_version}</strong></span>
                    <span>Fields: <strong className="text-slate-300">{comparison.run_a.field_count}</strong></span>
                    <span>Status: <strong className="text-emerald-400">{comparison.run_a.status}</strong></span>
                  </div>
                </div>

                <div className="bg-slate-800/60 border border-slate-700/80 rounded-lg p-4 space-y-2">
                  <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Run B (Candidate)</div>
                  <div className="text-sm font-bold text-slate-200">{comparison.run_b.id}</div>
                  <div className="text-xs text-slate-400 flex gap-4">
                    <span>Pipeline: <strong className="text-slate-300">{comparison.run_b.pipeline_version}</strong></span>
                    <span>Fields: <strong className="text-slate-300">{comparison.run_b.field_count}</strong></span>
                    <span>Status: <strong className="text-emerald-400">{comparison.run_b.status}</strong></span>
                  </div>
                </div>
              </div>

              {/* Field Diffs Table */}
              <div className="border border-slate-800 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400">
                    <tr>
                      <th className="py-2.5 px-4 font-semibold">Field / Canonical Key</th>
                      <th className="py-2.5 px-4 font-semibold">Run A Value</th>
                      <th className="py-2.5 px-4 font-semibold">Run B Value</th>
                      <th className="py-2.5 px-3 font-semibold text-center">Diff Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                    {comparison.field_diffs.map((diff) => (
                      <tr
                        key={diff.key}
                        className={diff.changed ? 'bg-amber-500/5 hover:bg-amber-500/10' : 'hover:bg-slate-800/30'}
                      >
                        <td className="py-2.5 px-4">
                          <div className="font-medium text-slate-200">{diff.label}</div>
                          <div className="text-[10px] text-slate-500 font-mono">{diff.key}</div>
                        </td>
                        <td className="py-2.5 px-4 text-slate-300">
                          <div>{String(diff.run_a.value ?? '—')}</div>
                          {diff.run_a.confidence !== null && (
                            <span className="text-[10px] text-slate-500">
                              conf: {Math.round(diff.run_a.confidence * 100)}%
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 text-slate-300">
                          <div>{String(diff.run_b.value ?? '—')}</div>
                          {diff.run_b.confidence !== null && (
                            <span className="text-[10px] text-slate-500">
                              conf: {Math.round(diff.run_b.confidence * 100)}%
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          {diff.changed ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-400/10 text-amber-300 border border-amber-400/20">
                              Changed
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-400/10 text-emerald-300 border border-emerald-400/20">
                              Identical
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/60 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-md transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
