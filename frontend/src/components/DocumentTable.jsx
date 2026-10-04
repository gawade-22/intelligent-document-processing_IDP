import React, { useState } from 'react';
import {
  Search,
  Filter,
  Upload,
  MoreVertical,
  Eye,
  CheckSquare,
  Play,
  Download,
  FileText,
  FileSpreadsheet,
  Image,
  ChevronDown,
  Trash2,
} from 'lucide-react';
import StatusBadge from './StatusBadge';
export default function DocumentTable({
  documents = [],
  total = 0,
  page = 1,
  pageSize = 10,
  totalPages = 1,
  onPageChange,
  onPageSizeChange,
  searchTerm = '',
  onSearchChange,
  currentStatusFilter = 'ALL',
  onStatusFilterChange,
  onViewDocument,
  onViewDetails,
  onReviewDocument,
  onVerifyDocument,
  onProcessDocument,
  onBatchProcess,
  onAdvancedFilter,
  onUploadClick,
  onDeleteDocument,
  onBatchDelete,
  isLoading = false,
  statusCounts = {},
  isDashboard = false,
}) {
  const [activeMenuId, setActiveMenuId] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);

  const toggleActionMenu = (id, e) => {
    e.stopPropagation();
    setActiveMenuId((prev) => (prev === id ? null : id));
  };

  React.useEffect(() => {
    const handleOutsideClick = () => setActiveMenuId(null);
    window.addEventListener('click', handleOutsideClick);
    return () => window.removeEventListener('click', handleOutsideClick);
  }, []);

  // Multi-select toggle
  const toggleSelectAll = () => {
    if (selectedIds.length === documents.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(documents.map((d) => d.id || d.document_id));
    }
  };

  const toggleSelectOne = (id, e) => {
    e.stopPropagation();
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const getFileTypeIcon = (type) => {
    const upper = (type || '').toUpperCase();
    if (upper === 'CSV') {
      return <FileText size={15} className="file-type-icon csv" />;
    }
    if (upper === 'XLSX' || upper === 'XLS' || upper === 'EXCEL') {
      return <FileSpreadsheet size={15} className="file-type-icon excel" />;
    }
    if (upper === 'PNG' || upper === 'JPG' || upper === 'JPEG' || upper === 'IMAGE') {
      return <Image size={15} className="file-type-icon image" />;
    }
    return <FileText size={15} className="file-type-icon pdf" />;
  };

  const getDocTypeBadge = (type) => {
    const t = (type || '').toLowerCase();
    const map = {
      invoice: { bg: '#eff6ff', color: '#1d4ed8', border: '#bfdbfe', label: 'Invoice' },
      purchase_order: { bg: '#e0e7ff', color: '#4338ca', border: '#c7d2fe', label: 'Purchase Order' },
      receipt: { bg: '#ecfdf5', color: '#047857', border: '#a7f3d0', label: 'Receipt' },
      bank_statement: { bg: '#ecfeff', color: '#0e7490', border: '#a5f3fc', label: 'Bank Statement' },
      resume: { bg: '#f3e8ff', color: '#6b21a8', border: '#d8b4fe', label: 'Resume/CV' },
      certificate: { bg: '#fef3c7', color: '#b45309', border: '#fde68a', label: 'Certificate' },
      contract: { bg: '#f1f5f9', color: '#334155', border: '#cbd5e1', label: 'Contract' },
      delivery_challan: { bg: '#fff7ed', color: '#c2410c', border: '#ffedd5', label: 'Delivery Challan' },
      medical_report: { bg: '#ffe4e6', color: '#be123c', border: '#fecdd3', label: 'Medical Report' },
      insurance: { bg: '#f0fdfa', color: '#0f766e', border: '#99f6e4', label: 'Insurance' },
      id_document: { bg: '#ede9fe', color: '#5b21b6', border: '#ddd6fe', label: 'ID Document' },
      expense_report: { bg: '#f7fee7', color: '#3f6212', border: '#d9f99d', label: 'Expense Report' },
      application_form: { bg: '#f0f9ff', color: '#0369a1', border: '#bae6fd', label: 'Application' },
    };
    return map[t] || { bg: '#f8fafc', color: '#475569', border: '#e2e8f0', label: type };
  };

  const formatConfidence = (doc) => {
    const conf = doc.confidence ?? doc.confidence_score;
    if (conf !== null && conf !== undefined) {
      const pct = conf <= 1.0 ? Math.round(conf * 100) : Math.round(conf);
      return (
        <span
          className={`conf-pill ${pct >= 85 ? 'high' : pct >= 65 ? 'medium' : 'low'}`}
          title={`Extraction Confidence: ${pct}%`}
        >
          {pct}%
        </span>
      );
    }
    return <span className="text-muted">—</span>;
  };

  const formatTimestamp = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return '—';
    }
  };

  const startEntry = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endEntry = Math.min(page * pageSize, total);

  // Quick filter tab options
  const filterTabs = [
    { id: 'ALL', label: 'All Documents', count: total },
    { id: 'NEEDS_REVIEW', label: 'Needs Review', count: statusCounts?.NEEDS_REVIEW ?? 0 },
    { id: 'VERIFIED', label: 'Verified', count: statusCounts?.VERIFIED ?? 0 },
    { id: 'PROCESSING', label: 'Processing', count: statusCounts?.PROCESSING ?? 0 },
    { id: 'FAILED', label: 'Failed', count: statusCounts?.FAILED ?? 0 },
  ];

  return (
    <div className="table-card">
      {/* 1. Quick Status Filter Tabs Bar (Only on full archive, or condensed on dashboard) */}
      {!isDashboard && onStatusFilterChange && (
        <div className="table-status-tabs-bar">
          <div className="tabs-list">
            {filterTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`status-tab-btn ${currentStatusFilter === tab.id ? 'active' : ''}`}
                onClick={() => onStatusFilterChange(tab.id)}
              >
                <span>{tab.label}</span>
                <span className="tab-count-badge">{tab.count}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 2. Top Table Controls Toolbar (Search bar + Filter & Upload Actions) */}
      <div className="table-toolbar">
        <div className="toolbar-left">
          {/* Search Bar matching reference */}
          <div className="search-box-wrapper">
            <span className="search-icon-prefix">
              <Search size={15} />
            </span>
            <input
              type="text"
              className="search-input"
              placeholder="Search documents..."
              value={searchTerm}
              onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
              aria-label="Search documents"
            />
          </div>
        </div>

        <div className="toolbar-right">
          {/* Quick Delete Selected Button */}
          {selectedIds.length > 0 && onBatchDelete && (
            <button
              type="button"
              className="btn btn-danger-subtle btn-sm"
              onClick={() => onBatchDelete(selectedIds, () => setSelectedIds([]))}
              title="Delete Selected Documents"
            >
              <Trash2 size={14} />
              <span>Delete ({selectedIds.length})</span>
            </button>
          )}

          {/* Advanced Filter Button */}
          {onAdvancedFilter && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onAdvancedFilter}
              title="Advanced Filter Options"
            >
              <Filter size={14} />
              <span>Advanced Filter</span>
            </button>
          )}

          {/* Upload Button */}
          {onUploadClick && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={onUploadClick}
              title="Upload New Document"
            >
              <Upload size={14} />
              <span>Upload</span>
            </button>
          )}
        </div>
      </div>

      {/* Batch Selection Banner if items selected */}
      {selectedIds.length > 0 && (
        <div className="batch-selection-banner">
          <div className="batch-selection-info">
            <span className="batch-count-pill">{selectedIds.length}</span>
            <span>document(s) selected</span>
          </div>
          <div className="batch-actions-buttons">
            <button
              type="button"
              className="btn-batch-action primary"
              onClick={() => onBatchProcess && onBatchProcess(selectedIds)}
            >
              <Play size={13} />
              <span>Process Selected</span>
            </button>
            {onBatchDelete && (
              <button
                type="button"
                className="btn-batch-action danger"
                onClick={() => onBatchDelete(selectedIds, () => setSelectedIds([]))}
                title="Delete Selected Documents"
              >
                <Trash2 size={13} />
                <span>Delete Selected</span>
              </button>
            )}
            <button
              type="button"
              className="btn-batch-action secondary"
              onClick={() => setSelectedIds([])}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* 3. Responsive Data Table */}
      <div className="table-responsive">
        <table className="data-table">
          <thead>
            <tr>
              <th className="col-checkbox">
                <input
                  type="checkbox"
                  checked={documents.length > 0 && selectedIds.length === documents.length}
                  onChange={toggleSelectAll}
                  className="table-checkbox"
                  aria-label="Select all documents"
                />
              </th>
              <th className="col-sr">SR. NO.</th>
              <th className="col-doc">DOCUMENT</th>
              <th className="col-type">TYPE</th>
              <th className="col-vendor">VENDOR / ENTITY</th>
              <th className="col-inv">IDENTIFIER / NO.</th>
              <th className="col-status">STATUS</th>
              <th className="col-conf">CONFIDENCE</th>
              <th className="col-date">UPDATED</th>
              <th className="col-actions">ACTION</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={10} className="table-loading-cell">
                  <div className="loading-spinner-box">
                    <span className="spinner-ring" />
                    <span>Loading documents from server...</span>
                  </div>
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={10} className="table-empty-cell">
                  <div className="empty-state-box">
                    <FileText size={38} className="empty-icon" />
                    <p className="empty-title">No documents available.</p>
                    <p className="empty-desc">
                      {searchTerm
                        ? `No documents match "${searchTerm}". Try a different keyword.`
                        : 'Get started by uploading your first document to begin processing.'}
                    </p>
                    {onUploadClick && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm mt-3"
                        onClick={onUploadClick}
                      >
                        <Upload size={14} />
                        <span>Upload your first document</span>
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              documents.map((doc, idx) => {
                const docId = doc.id || doc.document_id;
                const srNo = (page - 1) * pageSize + (idx + 1);
                const isMenuOpen = activeMenuId === docId;
                const isSelected = selectedIds.includes(docId);

                return (
                  <tr
                    key={docId}
                    className={`table-row ${isSelected ? 'row-selected' : ''}`}
                    onClick={() => onViewDetails ? onViewDetails(docId) : (onViewDocument && onViewDocument(doc))}
                  >
                    {/* Checkbox */}
                    <td className="col-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => toggleSelectOne(docId, e)}
                        className="table-checkbox"
                        aria-label={`Select document #${docId}`}
                      />
                    </td>

                    {/* SR. NO. */}
                    <td className="col-sr font-mono">{srNo}</td>

                    {/* DOCUMENT */}
                    <td className="col-doc">
                      <div className="doc-link-group">
                        {getFileTypeIcon(doc.file_type)}
                        <span className="doc-name-text" title={doc.file_name}>
                          {doc.file_name}
                        </span>
                      </div>
                    </td>

                    {/* TYPE */}
                    <td className="col-type">
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', alignItems: 'flex-start' }}>
                        <span className="file-format-pill">
                          {doc.file_type || 'PDF'}
                        </span>
                        {doc.document_type && (() => {
                          const badge = getDocTypeBadge(doc.document_type);
                          return (
                            <span
                              className="doc-type-badge-mini"
                              style={{
                                fontSize: '10px',
                                fontWeight: '600',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                backgroundColor: badge.bg,
                                color: badge.color,
                                border: `1px solid ${badge.border}`,
                                textTransform: 'capitalize',
                                letterSpacing: '0.2px',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {badge.label}
                            </span>
                          );
                        })()}
                      </div>
                    </td>

                    {/* VENDOR / ENTITY */}
                    <td className="col-vendor">
                      {(() => {
                        const entityName =
                          doc.vendor_name ||
                          doc.store_name ||
                          doc.account_holder ||
                          doc.candidate_name ||
                          doc.person_name ||
                          doc.patient_name ||
                          doc.buyer_name;
                        return entityName ? (
                          <span className="vendor-text" title={entityName}>
                            {entityName}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        );
                      })()}
                    </td>

                    {/* IDENTIFIER / NO. */}
                    <td className="col-inv">
                      {(() => {
                        const refNo =
                          doc.invoice_number ||
                          doc.receipt_number ||
                          doc.po_number ||
                          doc.account_number ||
                          doc.certificate_id ||
                          doc.id_number ||
                          doc.challan_number;
                        return refNo ? (
                          <span className="inv-no-text font-mono" title={refNo}>
                            {refNo}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        );
                      })()}
                    </td>

                    {/* STATUS using reusable StatusBadge */}
                    <td className="col-status">
                      <StatusBadge status={doc.status} />
                    </td>

                    {/* CONFIDENCE */}
                    <td className="col-conf font-mono">
                      {formatConfidence(doc)}
                    </td>

                    {/* UPDATED */}
                    <td className="col-date font-mono text-muted text-xs">
                      {formatTimestamp(doc.updated_at || doc.uploaded_at)}
                    </td>

                    {/* ACTION MENU */}
                    <td className="col-actions" onClick={(e) => e.stopPropagation()}>
                      <div className="table-actions-cell-wrapper">
                        {onDeleteDocument && (
                          <button
                            type="button"
                            className="table-action-btn delete-action-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteDocument(doc);
                            }}
                            title={`Delete ${doc.file_name}`}
                            aria-label={`Delete ${doc.file_name}`}
                          >
                            <Trash2 size={15} />
                          </button>
                        )}

                        <div className="action-menu-container">
                          <button
                            type="button"
                            className="action-menu-trigger"
                            onClick={(e) => toggleActionMenu(docId, e)}
                            aria-label="Document actions"
                            title="Actions"
                          >
                            ⋮
                          </button>

                          {isMenuOpen && (
                            <div className="action-dropdown-menu" role="menu">
                              <button
                                type="button"
                                className="dropdown-item"
                                role="menuitem"
                                onClick={() => {
                                  setActiveMenuId(null);
                                  if (onViewDetails) {
                                    onViewDetails(docId);
                                  } else if (onViewDocument) {
                                    onViewDocument(doc);
                                  }
                                }}
                              >
                                <Eye size={14} className="dropdown-icon" />
                                <span>View Details</span>
                              </button>

                              {(doc.status === 'NEEDS_REVIEW' || doc.needs_review) && (
                                <button
                                  type="button"
                                  className="dropdown-item highlight"
                                  role="menuitem"
                                  onClick={() => {
                                    setActiveMenuId(null);
                                    if (onReviewDocument) {
                                      onReviewDocument(doc);
                                    } else if (onVerifyDocument) {
                                      onVerifyDocument(doc);
                                    }
                                  }}
                                >
                                  <CheckSquare size={14} className="dropdown-icon" />
                                  <span>Review</span>
                                </button>
                              )}

                              {onDeleteDocument && (
                                <button
                                  type="button"
                                  className="dropdown-item danger"
                                  role="menuitem"
                                  onClick={() => {
                                    setActiveMenuId(null);
                                    onDeleteDocument(doc);
                                  }}
                                >
                                  <Trash2 size={14} className="dropdown-icon" />
                                  <span>Delete Document</span>
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* 4. Table Pagination Footer */}
      {isDashboard ? (
        <div className="table-pagination-footer table-pagination-dashboard">
          <div className="pagination-info">
            Showing <strong>{documents.length > 0 ? 1 : 0}</strong> to{' '}
            <strong>{documents.length}</strong> of <strong>{total}</strong> recent documents
          </div>
          {onAdvancedFilter && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onAdvancedFilter}
              style={{ fontSize: '12px', padding: '4px 10px' }}
            >
              <span>View All</span>
              &rarr;
            </button>
          )}
        </div>
      ) : (
        <div className="table-pagination-footer">
          <div className="pagination-info">
            Showing <strong>{startEntry}</strong> to <strong>{endEntry}</strong> of{' '}
            <strong>{total}</strong> entries
          </div>

          <div className="pagination-controls">
            <div className="entries-select-wrapper">
              <span className="text-xs text-muted">Show</span>
              <select
                className="entries-select"
                value={pageSize}
                onChange={(e) => onPageSizeChange && onPageSizeChange(Number(e.target.value))}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </div>

            <button
              type="button"
              className="pagination-btn"
              disabled={page <= 1}
              onClick={() => onPageChange && onPageChange(page - 1)}
            >
              Previous
            </button>

            <span className="pagination-page-current font-mono">
              {page} / {Math.max(1, totalPages)}
            </span>

            <button
              type="button"
              className="pagination-btn"
              disabled={page >= totalPages}
              onClick={() => onPageChange && onPageChange(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
