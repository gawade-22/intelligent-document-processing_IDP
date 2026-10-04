import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Save,
  Plus,
  Trash2,
  RefreshCw,
  Download,
  Copy,
  Check,
  Search,
  Receipt,
  ShoppingCart,
  Landmark,
  UserCheck,
  Award,
  GraduationCap,
  FileCheck2,
  Truck,
  HeartPulse,
  Shield,
  CreditCard,
  DollarSign,
  ClipboardList,
  FileSpreadsheet,
  ListPlus,
  Table as TableIcon,
} from 'lucide-react';
import {
  fetchDocumentDetails,
  verifyDocument,
  processDocument,
  getDocumentFileUrl,
} from '../services/api';

const DOC_TYPE_META = {
  invoice: { label: 'Commercial Invoice', bg: '#ecfdf5', text: '#065f46', border: '#a7f3d0', icon: FileSpreadsheet },
  purchase_order: { label: 'Purchase Order', bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe', icon: ShoppingCart },
  receipt: { label: 'Store / Retail Receipt', bg: '#fffbeb', text: '#92400e', border: '#fde68a', icon: Receipt },
  bank_statement: { label: 'Bank Statement', bg: '#f0fdfa', text: '#115e59', border: '#99f6e4', icon: Landmark },
  resume: { label: 'Resume / CV', bg: '#faf5ff', text: '#6b21a8', border: '#e9d5ff', icon: UserCheck },
  cv: { label: 'Curriculum Vitae', bg: '#faf5ff', text: '#6b21a8', border: '#e9d5ff', icon: UserCheck },
  certificate: { label: 'Certificate', bg: '#fff1f2', text: '#9f1239', border: '#fecdd3', icon: Award },
  student_document: { label: 'Student Document / Marksheet', bg: '#fff1f2', text: '#9f1239', border: '#fecdd3', icon: GraduationCap },
  contract: { label: 'Contract / Agreement', bg: '#f8fafc', text: '#334155', border: '#cbd5e1', icon: FileCheck2 },
  delivery_challan: { label: 'Delivery Challan', bg: '#fdf4ff', text: '#86198f', border: '#f5d0fe', icon: Truck },
  medical_report: { label: 'Medical Report', bg: '#fef2f2', text: '#991b1b', border: '#fecaca', icon: HeartPulse },
  insurance: { label: 'Insurance Policy', bg: '#f0fdf4', text: '#166534', border: '#bbf7d0', icon: Shield },
  id_document: { label: 'Identity Document', bg: '#f0f9ff', text: '#075985', border: '#bae6fd', icon: CreditCard },
  expense_report: { label: 'Expense Report', bg: '#f7fee7', text: '#3f6212', border: '#d9f99d', icon: DollarSign },
  application_form: { label: 'Application Form', bg: '#f0f9ff', text: '#0369a1', border: '#bae6fd', icon: ClipboardList },
  custom: { label: 'Universal Document', bg: '#f1f5f9', text: '#475569', border: '#cbd5e1', icon: FileText },
  unknown: { label: 'Unclassified Document', bg: '#f1f5f9', text: '#475569', border: '#cbd5e1', icon: FileText },
};

const MULTILINE_FIELDS = new Set([
  'terms_summary',
  'summary',
  'description',
  'address',
  'experience',
  'education',
  'projects',
  'form_fields',
  'transaction_description',
  'key_values',
  'key_entities',
  'notes',
]);

const ARRAY_FIELDS = new Set([
  'items',
  'skills',
  'primary_parties',
  'key_dates',
  'line_items',
  'transactions',
]);

const getFieldHumanLabel = (key) => {
  const labelMap = {
    vendor_name: 'Vendor Name',
    invoice_number: 'Invoice No.',
    invoice_date: 'Invoice Date',
    items: 'Line Items',
    quantity: 'Quantity',
    tax_amount: 'Tax Amount',
    total_amount: 'Total Amount',
    po_number: 'PO Number',
    buyer_name: 'Buyer Name',
    supplier_name: 'Supplier Name',
    order_date: 'Order Date',
    unit_price: 'Unit Price',
    store_name: 'Store / Merchant Name',
    receipt_number: 'Receipt No.',
    receipt_date: 'Receipt Date',
    subtotal_amount: 'Subtotal Amount',
    payment_method: 'Payment Method',
    account_holder: 'Account Holder',
    account_number: 'Account No.',
    statement_period: 'Statement Period',
    transaction_date: 'Transaction Date',
    transaction_description: 'Transaction Description',
    debit_amount: 'Debit Amount',
    credit_amount: 'Credit Amount',
    balance_amount: 'Account Balance',
    candidate_name: 'Candidate Name',
    email: 'Email Address',
    phone: 'Phone Number',
    skills: 'Technical Skills',
    education: 'Education',
    experience: 'Work Experience',
    projects: 'Projects',
    person_name: 'Person Name',
    student_name: 'Student Name',
    roll_number: 'Roll / PRN No.',
    percentage: 'Percentage / CGPA',
    college: 'Institution / College',
    certificate_type: 'Certificate Type',
    institution_name: 'Issuing Institution',
    issue_date: 'Issue Date',
    certificate_id: 'Certificate ID',
    parties: 'Parties Involved',
    agreement_date: 'Agreement Date',
    effective_date: 'Effective Date',
    expiry_date: 'Expiry Date',
    contract_value: 'Contract Value',
    terms_summary: 'Terms & Conditions',
    challan_number: 'Challan No.',
    challan_date: 'Challan Date',
    customer_name: 'Customer Name',
    transport_details: 'Transport Details',
    patient_name: 'Patient Name',
    report_date: 'Report Date',
    test_name: 'Test / Investigation',
    test_result: 'Observed Result',
    reference_range: 'Reference Interval',
    doctor_name: 'Doctor Name',
    policy_number: 'Policy No.',
    policy_holder: 'Policy Holder',
    insurance_type: 'Insurance Type',
    start_date: 'Start Date',
    premium_amount: 'Premium Amount',
    id_number: 'ID / Card Number',
    date_of_birth: 'Date of Birth',
    address: 'Address',
    issue_expiry_date: 'Issue / Expiry Date',
    employee_name: 'Employee Name',
    expense_date: 'Expense Date',
    category: 'Category',
    description: 'Description',
    expense_amount: 'Expense Amount',
    applicant_name: 'Applicant Name',
    contact_details: 'Contact Details',
    application_number: 'Application No.',
    document_title: 'Document Title',
    document_category: 'Inferred Category',
    summary: 'Executive Summary',
    key_entities: 'Discovered Entities',
    key_values: 'Key Values & Metrics',
  };
  return labelMap[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

function tryParseArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // Handle Python list format: ['item1', 'item2']
      try {
        const cleaned = trimmed
          .replace(/^\[\s*/, '')
          .replace(/\s*\]$/, '')
          .split(/,\s*(?=(?:[^'"]*['"][^'"]*['"])*[^'"]*$)/)
          .map((item) => item.replace(/^['"]\s*/, '').replace(/\s*['"]$/, '').trim())
          .filter(Boolean);
        if (cleaned.length > 0) return cleaned;
      } catch {
        return null;
      }
    }
  }
  return null;
}

export default function DocumentViewerModal({
  docId,
  isOpen,
  onClose,
  onUpdateSuccess,
}) {
  const [docDetails, setDocDetails] = useState(null);
  const [editedFields, setEditedFields] = useState({});
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [copiedJson, setCopiedJson] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (isOpen && docId) {
      loadDetails();
    } else {
      setDocDetails(null);
      setEditedFields({});
      setMessage(null);
      setErrorMsg(null);
      setSearchQuery('');
      setCopiedJson(false);
    }
  }, [isOpen, docId]);

  const loadDetails = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await fetchDocumentDetails(docId);
      setDocDetails(data);

      const initialFields = {};
      if (data.fields) {
        Object.entries(data.fields).forEach(([key, fieldObj]) => {
          const val = fieldObj.normalized_value !== null && fieldObj.normalized_value !== undefined
            ? fieldObj.normalized_value
            : fieldObj.value ?? '';
          
          const parsedArr = tryParseArray(val);
          initialFields[key] = parsedArr !== null ? parsedArr : val;
        });
      }
      setEditedFields(initialFields);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load document details');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFieldChange = (key, val) => {
    setEditedFields((prev) => ({
      ...prev,
      [key]: val,
    }));
  };

  const handleArrayItemChange = (fieldKey, itemIdx, newVal) => {
    setEditedFields((prev) => {
      const currentList = Array.isArray(prev[fieldKey]) ? [...prev[fieldKey]] : [];
      currentList[itemIdx] = newVal;
      return {
        ...prev,
        [fieldKey]: currentList,
      };
    });
  };

  const handleRemoveArrayItem = (fieldKey, itemIdx) => {
    setEditedFields((prev) => {
      const currentList = Array.isArray(prev[fieldKey]) ? [...prev[fieldKey]] : [];
      currentList.splice(itemIdx, 1);
      return {
        ...prev,
        [fieldKey]: currentList,
      };
    });
  };

  const handleAddArrayItem = (fieldKey) => {
    setEditedFields((prev) => {
      const currentList = Array.isArray(prev[fieldKey]) ? [...prev[fieldKey]] : [];
      currentList.push('');
      return {
        ...prev,
        [fieldKey]: currentList,
      };
    });
  };

  const handleAddNewField = (e) => {
    e.preventDefault();
    if (!newFieldName.trim()) return;

    const parsed = tryParseArray(newFieldValue);
    setEditedFields((prev) => ({
      ...prev,
      [newFieldName.trim()]: parsed !== null ? parsed : newFieldValue,
    }));
    setNewFieldName('');
    setNewFieldValue('');
  };

  const handleSaveVerification = async () => {
    setIsSaving(true);
    setMessage(null);
    setErrorMsg(null);

    try {
      const payloadFields = {};
      Object.entries(editedFields).forEach(([k, v]) => {
        if (Array.isArray(v)) {
          payloadFields[k] = JSON.stringify(v);
        } else {
          payloadFields[k] = v;
        }
      });

      const result = await verifyDocument(docId, payloadFields);
      setMessage(result.message || 'Corrections saved and re-validated successfully.');
      if (onUpdateSuccess) onUpdateSuccess();
      await loadDetails();
    } catch (err) {
      setErrorMsg(err.message || 'Verification save failed');
    } finally {
      setIsSaving(false);
    }
  };

  const handleTriggerPipeline = async () => {
    setIsProcessing(true);
    setMessage(null);
    setErrorMsg(null);
    try {
      await processDocument(docId);
      setMessage('Document re-processed through the IDP pipeline.');
      if (onUpdateSuccess) onUpdateSuccess();
      await loadDetails();
    } catch (err) {
      setErrorMsg(err.message || 'Pipeline execution failed');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyJson = () => {
    const jsonStr = JSON.stringify(
      {
        document_id: docDetails?.document_id,
        file_name: docDetails?.file_name,
        document_type: docDetails?.document_type,
        status: docDetails?.status,
        confidence_score: docDetails?.confidence_score,
        fields: editedFields,
      },
      null,
      2
    );
    navigator.clipboard.writeText(jsonStr);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  const filteredFieldKeys = useMemo(() => {
    if (!editedFields) return [];
    const keys = Object.keys(editedFields);
    if (!searchQuery.trim()) return keys;
    const q = searchQuery.toLowerCase();
    return keys.filter(
      (k) =>
        k.toLowerCase().includes(q) ||
        getFieldHumanLabel(k).toLowerCase().includes(q) ||
        String(editedFields[k]).toLowerCase().includes(q)
    );
  }, [editedFields, searchQuery]);

  if (!isOpen || !docId) return null;

  const fileUrl = getDocumentFileUrl(docId);
  const isPdf =
    docDetails?.file_type?.toUpperCase() === 'PDF' ||
    docDetails?.file_name?.toLowerCase().endsWith('.pdf');
  const isImage =
    ['PNG', 'JPG', 'JPEG'].includes(docDetails?.file_type?.toUpperCase()) ||
    /\.(png|jpg|jpeg)$/i.test(docDetails?.file_name || '');

  const docTypeKey = (docDetails?.document_type || 'custom').toLowerCase();
  const typeMeta = DOC_TYPE_META[docTypeKey] || DOC_TYPE_META.custom;
  const TypeIcon = typeMeta.icon || FileText;

  const overallScore =
    docDetails?.confidence_score !== null && docDetails?.confidence_score !== undefined
      ? Math.round(docDetails.confidence_score * 100)
      : null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="viewer-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="viewer-modal-header">
          <div className="viewer-title-row">
            <TypeIcon size={20} className="viewer-title-icon" style={{ color: typeMeta.text }} />
            <div className="viewer-heading-group">
              <h2 className="viewer-title">{docDetails?.file_name || `Document #${docId}`}</h2>
              <div className="viewer-badges-row">
                <span
                  className="badge-doc-type"
                  style={{
                    backgroundColor: typeMeta.bg,
                    color: typeMeta.text,
                    border: `1px solid ${typeMeta.border}`,
                  }}
                >
                  <TypeIcon size={12} />
                  <span>{docDetails?.document_type_label || typeMeta.label}</span>
                </span>
                <span className={`status-pill status-${docDetails?.status?.toLowerCase()}`}>
                  {docDetails?.status}
                </span>
              </div>
            </div>
          </div>

          <div className="viewer-header-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleCopyJson}
              title="Copy structured extracted JSON to clipboard"
            >
              {copiedJson ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
              <span>{copiedJson ? 'Copied JSON!' : 'Copy JSON'}</span>
            </button>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleTriggerPipeline}
              disabled={isProcessing}
              title="Re-run the automated extraction pipeline"
            >
              <RefreshCw size={14} className={isProcessing ? 'spinning' : ''} />
              <span>{isProcessing ? 'Processing...' : 'Re-run Pipeline'}</span>
            </button>

            <a
              href={fileUrl}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm"
              download
              title="Download original file"
            >
              <Download size={14} />
              <span>Download</span>
            </a>

            <button
              type="button"
              className="modal-close-btn"
              onClick={onClose}
              aria-label="Close"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Modal Body - 2 Columns */}
        <div className="viewer-modal-body">
          {isLoading ? (
            <div className="viewer-loading-state">
              <span className="spinner-ring" />
              <p>Loading document details, classification, and preview...</p>
            </div>
          ) : (
            <>
              {/* Left Column: Document File Preview */}
              <div className="viewer-left-column">
                <div className="preview-header">
                  <span className="preview-label">ORIGINAL DOCUMENT PREVIEW</span>
                  <a
                    href={fileUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="preview-open-link"
                  >
                    <span>Open in new tab</span>
                    <ExternalLink size={13} />
                  </a>
                </div>

                <div className="preview-content-box">
                  {isPdf ? (
                    <iframe
                      src={fileUrl}
                      title="PDF Document Preview"
                      className="pdf-preview-iframe"
                    />
                  ) : isImage ? (
                    <div className="image-preview-wrapper">
                      <img
                        src={fileUrl}
                        alt="Document Preview"
                        className="image-preview-element"
                      />
                    </div>
                  ) : (
                    <div className="unsupported-preview-box">
                      <FileText size={48} className="unsupported-icon" />
                      <p>Tabular / Structured File ({docDetails?.file_type})</p>
                      <a href={fileUrl} className="btn btn-primary btn-sm" download>
                        Download File to Inspect
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Extracted Fields & Human Verification */}
              <div className="viewer-right-column">
                <div className="fields-panel-header">
                  <div className="panel-title-group">
                    <span className="panel-title">Extracted Data & Verification</span>
                    <span className="panel-subtitle">Review confidence, edit fields, and verify data</span>
                  </div>

                  {overallScore !== null && (
                    <div
                      className="overall-score-badge"
                      style={{
                        backgroundColor: overallScore >= 85 ? '#ecfdf5' : overallScore >= 70 ? '#fffbeb' : '#fef2f2',
                        color: overallScore >= 85 ? '#065f46' : overallScore >= 70 ? '#92400e' : '#991b1b',
                        border: `1px solid ${overallScore >= 85 ? '#a7f3d0' : overallScore >= 70 ? '#fde68a' : '#fecaca'}`,
                      }}
                    >
                      <span>Overall: </span>
                      <strong>{overallScore}%</strong>
                    </div>
                  )}
                </div>

                {/* Status messages */}
                {message && (
                  <div className="alert-box alert-success sm" style={{ margin: '10px 16px 0' }}>
                    <CheckCircle2 size={15} />
                    <span>{message}</span>
                  </div>
                )}
                {errorMsg && (
                  <div className="alert-box alert-error sm" style={{ margin: '10px 16px 0' }}>
                    <AlertTriangle size={15} />
                    <span>{errorMsg}</span>
                  </div>
                )}

                {/* Validation Errors Notice */}
                {docDetails?.validation_errors?.length > 0 && (
                  <div className="validation-errors-box">
                    <div className="val-error-title">
                      <AlertTriangle size={14} />
                      <span>Validation Notices:</span>
                    </div>
                    <ul className="val-error-list">
                      {docDetails.validation_errors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Field Search Bar */}
                <div className="fields-search-bar">
                  <Search size={14} className="search-icon" />
                  <input
                    type="text"
                    placeholder="Search extracted fields or values..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="fields-search-input"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      className="search-clear-btn"
                      onClick={() => setSearchQuery('')}
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>

                {/* Editable Fields List */}
                <div className="fields-list-scroll">
                  {filteredFieldKeys.length === 0 ? (
                    <div className="no-fields-notice">
                      <p>No matching fields found for "{searchQuery}"</p>
                    </div>
                  ) : (
                    filteredFieldKeys.map((key) => {
                      const val = editedFields[key];
                      const meta = docDetails?.fields?.[key] || {};
                      const conf = meta.confidence;
                      const source = meta.source;
                      const isArrayVal = Array.isArray(val);
                      const isMultiLine = MULTILINE_FIELDS.has(key);

                      const confColor =
                        conf >= 0.85
                          ? '#059669'
                          : conf >= 0.70
                          ? '#d97706'
                          : conf > 0
                          ? '#dc2626'
                          : '#94a3b8';

                      return (
                        <div key={key} className="field-edit-row">
                          <div className="field-meta-bar">
                            <label className="field-label-text">
                              {isArrayVal && <ListPlus size={12} className="inline-icon" />}
                              {getFieldHumanLabel(key)}
                            </label>
                            <div className="field-tags">
                              {source && (
                                <span className={`source-tag tag-${source.toLowerCase()}`}>
                                  {source}
                                </span>
                              )}
                              {conf !== null && conf !== undefined && (
                                <span
                                  className="conf-tag"
                                  style={{
                                    color: confColor,
                                    fontWeight: '700',
                                  }}
                                >
                                  {Math.round(conf * 100)}%
                                </span>
                              )}
                            </div>
                          </div>

                          {isArrayVal ? (
                            <div className="array-items-container">
                              {val.length === 0 ? (
                                <div className="empty-array-notice">No items listed</div>
                              ) : (
                                val.map((item, itemIdx) => (
                                  <div key={itemIdx} className="array-item-row">
                                    <span className="array-item-index">#{itemIdx + 1}</span>
                                    <input
                                      type="text"
                                      className="field-text-input array-item-input"
                                      value={typeof item === 'object' ? JSON.stringify(item) : (item || '')}
                                      placeholder={`Item ${itemIdx + 1}...`}
                                      onChange={(e) =>
                                        handleArrayItemChange(key, itemIdx, e.target.value)
                                      }
                                    />
                                    <button
                                      type="button"
                                      className="array-item-remove-btn"
                                      onClick={() => handleRemoveArrayItem(key, itemIdx)}
                                      title="Remove item"
                                    >
                                      <Trash2 size={13} />
                                    </button>
                                  </div>
                                ))
                              )}
                              <button
                                type="button"
                                className="btn-add-array-item"
                                onClick={() => handleAddArrayItem(key)}
                              >
                                <Plus size={13} />
                                <span>Add {getFieldHumanLabel(key)} Item</span>
                              </button>
                            </div>
                          ) : isMultiLine ? (
                            <textarea
                              className="field-textarea-input"
                              rows={3}
                              value={val || ''}
                              placeholder={`Enter ${getFieldHumanLabel(key)}...`}
                              onChange={(e) => handleFieldChange(key, e.target.value)}
                            />
                          ) : (
                            <input
                              type="text"
                              className="field-text-input"
                              value={val || ''}
                              placeholder={`Enter ${getFieldHumanLabel(key)}...`}
                              onChange={(e) => handleFieldChange(key, e.target.value)}
                            />
                          )}
                        </div>
                      );
                    })
                  )}

                  {/* Add Missing Field Box */}
                  <div className="add-field-box">
                    <span className="add-field-title">+ Add Missing Field</span>
                    <div className="add-field-inputs">
                      <input
                        type="text"
                        placeholder="Field name (e.g. tax_amount)"
                        value={newFieldName}
                        onChange={(e) => setNewFieldName(e.target.value)}
                        className="add-name-input"
                      />
                      <input
                        type="text"
                        placeholder="Value"
                        value={newFieldValue}
                        onChange={(e) => setNewFieldValue(e.target.value)}
                        className="add-val-input"
                      />
                      <button
                        type="button"
                        onClick={handleAddNewField}
                        className="btn btn-secondary btn-sm"
                        disabled={!newFieldName.trim()}
                      >
                        <Plus size={14} />
                        <span>Add</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Verification Footer Action */}
                <div className="fields-panel-footer">
                  <button
                    type="button"
                    className="btn btn-primary full-width"
                    onClick={handleSaveVerification}
                    disabled={isSaving}
                  >
                    {isSaving ? (
                      <>
                        <span className="spinner-ring sm" />
                        <span>Saving & Re-validating...</span>
                      </>
                    ) : (
                      <>
                        <Save size={16} />
                        <span>Save Verification & Mark Verified</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
