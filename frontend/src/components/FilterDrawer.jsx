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

  const formatOptions = [
    { value: 'ALL', label: 'All File Formats' },
    { value: 'PDF', label: 'PDF Documents' },
    { value: 'IMAGE', label: 'Scanned Images (PNG / JPG / JPEG)' },
    { value: 'CSV', label: 'CSV Spreadsheets' },
    { value: 'XLSX', label: 'Excel (XLSX)' },
  ];

  const categoryOptions = [
    { value: 'ALL', label: 'All Document Categories' },
    { value: 'INVOICE', label: 'Commercial Invoice' },
    { value: 'RECEIPT', label: 'Store / Retail Receipt' },
    { value: 'PURCHASE_ORDER', label: 'Purchase Order (PO)' },
    { value: 'BANK_STATEMENT', label: 'Bank Statement' },
    { value: 'RESUME', label: 'Resume / CV' },
    { value: 'CERTIFICATE', label: 'Certificate / Academic Record' },
    { value: 'CONTRACT', label: 'Contract / Agreement' },
    { value: 'DELIVERY_CHALLAN', label: 'Delivery Challan' },
    { value: 'MEDICAL_REPORT', label: 'Medical Lab Report' },
    { value: 'INSURANCE', label: 'Insurance Policy' },
    { value: 'ID_DOCUMENT', label: 'Identity Document' },
    { value: 'EXPENSE_REPORT', label: 'Expense Report' },
    { value: 'APPLICATION_FORM', label: 'Application Form' },
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

          {/* Document Category Filter */}
          <div className="filter-group">
            <label className="filter-label">Document Category / Domain</label>
            <select
              className="filter-select"
              value={filters.category || 'ALL'}
              onChange={(e) => {
                const val = e.target.value;
                onFilterChange('category', val);
                onFilterChange('documentType', val);
              }}
            >
              {categoryOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* File Format Filter */}
          <div className="filter-group">
            <label className="filter-label">File Format</label>
            <select
              className="filter-select"
              value={filters.fileFormat || 'ALL'}
              onChange={(e) => {
                const val = e.target.value;
                onFilterChange('fileFormat', val);
                if (val !== 'ALL') {
                  onFilterChange('documentType', val);
                }
              }}
            >
              {formatOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Vendor / Entity Search */}
          <div className="filter-group">
            <label className="filter-label">Vendor / Entity / Person Name</label>
            <input
              type="text"
              className="filter-input"
              placeholder="e.g. Metro de Madrid, Acme, Ayush, etc."
              value={filters.vendorName || ''}
              onChange={(e) => onFilterChange('vendorName', e.target.value)}
            />
          </div>

          {/* Identifier Search */}
          <div className="filter-group">
            <label className="filter-label">Invoice / Reference / Slip Number</label>
            <input
              type="text"
              className="filter-input"
              placeholder="e.g. INV-1001, REC-8841, etc."
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
