import React from 'react';
import { X, Filter, RotateCcw, Check } from 'lucide-react';

export default function FilterDrawer({
  isOpen,
  onClose,
  filters,
  onFilterChange,
  onResetFilters,
  onApplyFilters,
}) {
  if (!isOpen) return null;

  const statusOptions = [
    { value: 'ALL', label: 'All Statuses' },
    { value: 'NEEDS_REVIEW', label: 'Needs Review / Awaiting Verification' },
    { value: 'VERIFIED', label: 'Verified & Accepted' },
    { value: 'FAILED', label: 'Processing Failed' },
    { value: 'PROCESSING', label: 'Processing' },
    { value: 'UPLOADED', label: 'Uploaded' },
  ];

  const typeOptions = [
    { value: 'ALL', label: 'All Document Types' },
    { value: 'PDF', label: 'PDF Documents' },
    { value: 'IMAGE', label: 'Images (PNG / JPG / JPEG)' },
    { value: 'CSV', label: 'CSV Spreadsheets' },
    { value: 'XLSX', label: 'Excel (XLSX)' },
    { value: 'INVOICE', label: 'Invoices' },
  ];

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer-container" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <Filter size={18} className="drawer-icon" />
            <h3 className="drawer-title">Advanced Document Filters</h3>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close filters"
          >
            <X size={18} />
          </button>
        </div>

        <div className="drawer-body">
          {/* Status Filter */}
          <div className="filter-group">
            <label className="filter-label">Document Status</label>
            <select
              className="filter-select"
              value={filters.status || 'ALL'}
              onChange={(e) => onFilterChange('status', e.target.value)}
            >
              {statusOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Type Filter */}
          <div className="filter-group">
            <label className="filter-label">File / Document Format</label>
            <select
              className="filter-select"
              value={filters.documentType || 'ALL'}
              onChange={(e) => onFilterChange('documentType', e.target.value)}
            >
              {typeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Vendor Search */}
          <div className="filter-group">
            <label className="filter-label">Vendor Name</label>
            <input
              type="text"
              className="filter-input"
              placeholder="e.g. Techno Fiber, Acme, etc."
              value={filters.vendorName || ''}
              onChange={(e) => onFilterChange('vendorName', e.target.value)}
            />
          </div>

          {/* Invoice Number Search */}
          <div className="filter-group">
            <label className="filter-label">Invoice / Document Number</label>
            <input
              type="text"
              className="filter-input"
              placeholder="e.g. INV-1001, TF/26-27/078"
              value={filters.invoiceNumber || ''}
              onChange={(e) => onFilterChange('invoiceNumber', e.target.value)}
            />
          </div>
        </div>

        <div className="drawer-footer">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onResetFilters}
          >
            <RotateCcw size={14} />
            <span>Reset</span>
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onApplyFilters}
          >
            <Check size={14} />
            <span>Apply Filters</span>
          </button>
        </div>
      </div>
    </div>
  );
}
