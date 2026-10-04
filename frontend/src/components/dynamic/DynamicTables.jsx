import React, { useState } from 'react';
import {
  Table as TableIcon,
  Download,
  FileSpreadsheet,
  Layers,
  ChevronDown,
  ChevronRight,
  MapPin,
} from 'lucide-react';

export default function DynamicTables({ tables = [], onSelectEvidence }) {
  const [collapsedTables, setCollapsedTables] = useState({});

  if (!tables || tables.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
        <TableIcon size={36} className="mx-auto mb-2 opacity-50 text-slate-400" />
        <p className="font-semibold text-sm text-slate-600">No tables extracted</p>
        <p className="text-xs text-slate-400 mt-1">
          No structured tables or line items were found in this document.
        </p>
      </div>
    );
  }

  const toggleTable = (id) => {
    setCollapsedTables((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const exportTableToCsv = (tbl) => {
    const headers = tbl.headers || [];
    const rows = tbl.rows || [];
    const csvContent = [
      headers.join(','),
      ...rows.map((row) =>
        (Array.isArray(row) ? row : Object.values(row))
          .map((c) => `"${String(c || '').replace(/"/g, '""')}"`)
          .join(',')
      ),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.setAttribute('download', `${tbl.title || 'extracted_table'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {tables.map((tbl, idx) => {
        const tableId = tbl.id || `tbl_${idx}`;
        const isCollapsed = collapsedTables[tableId];
        const headers = tbl.headers || [];
        const rows = tbl.rows || [];

        return (
          <div key={tableId} className="uv-section-card">
            <div className="uv-section-header" onClick={() => toggleTable(tableId)}>
              <div className="flex items-center gap-2">
                {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                <FileSpreadsheet size={16} className="text-emerald-600" />
                <span className="font-bold text-sm text-slate-800">
                  {tbl.title || `Table #${idx + 1}`}
                </span>
                <span className="text-xs text-slate-400 font-normal">
                  ({rows.length} rows, {headers.length} columns)
                </span>
              </div>

              <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                {tbl.source?.page && (
                  <button
                    type="button"
                    className="uv-badge uv-badge-family hover:bg-slate-200"
                    onClick={() => onSelectEvidence && onSelectEvidence({ evidence: tbl.source })}
                    title={`Jump to page ${tbl.source.page}`}
                  >
                    <MapPin size={11} /> Page {tbl.source.page}
                  </button>
                )}
                <button
                  type="button"
                  className="uv-icon-btn bg-white hover:bg-slate-50 text-slate-700 border-slate-200"
                  onClick={() => exportTableToCsv(tbl)}
                  title="Export table as CSV"
                >
                  <Download size={12} />
                  <span>CSV</span>
                </button>
              </div>
            </div>

            {!isCollapsed && (
              <div className="p-4">
                <div className="uv-table-wrapper">
                  <table className="uv-table">
                    <thead>
                      <tr>
                        <th className="w-10 text-center text-slate-400 font-mono">#</th>
                        {headers.map((h, hIdx) => (
                          <th key={hIdx}>{h.replace(/_/g, ' ')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.length === 0 ? (
                        <tr>
                          <td colSpan={headers.length + 1} className="text-center py-6 text-slate-400">
                            No rows extracted
                          </td>
                        </tr>
                      ) : (
                        rows.map((row, rIdx) => {
                          const cells = Array.isArray(row) ? row : headers.map((h) => row[h]);
                          return (
                            <tr key={rIdx}>
                              <td className="text-center font-mono text-xs text-slate-400">
                                {rIdx + 1}
                              </td>
                              {cells.map((cell, cIdx) => (
                                <td key={cIdx}>{cell !== null && cell !== undefined ? String(cell) : '—'}</td>
                              ))}
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
      })}
    </div>
  );
}
