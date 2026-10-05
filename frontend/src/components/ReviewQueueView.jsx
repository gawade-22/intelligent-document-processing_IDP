import React, { useState, useEffect, useMemo } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Search,
  CheckSquare,
  ArrowRight,
  FileText,
  FileSpreadsheet,
  Image as ImageIcon,
  Clock,
  Tag,
} from 'lucide-react';
import { fetchDocuments } from '../services/api';

/**
 * Helper to dynamically extract key-value fields from a document
 * without hardcoding any specific schema (invoice, medical, student, etc.)
 */
function getDynamicFields(doc) {
  const fields = [];

  // 1. If doc.fields exists as an object/map
  if (doc.fields && typeof doc.fields === 'object' && !Array.isArray(doc.fields)) {
    for (const [key, valObj] of Object.entries(doc.fields)) {
      let val = null;
      if (valObj !== null && typeof valObj === 'object') {
        val = valObj.value ?? valObj.normalized_value ?? valObj.text;
      } else if (valObj !== null && valObj !== undefined) {
        val = valObj;
      }
      if (val !== null && val !== undefined && String(val).trim() !== '') {
        const formattedKey = key
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());
        fields.push({
          key,
          label: formattedKey,
          value: String(val),
        });
      }
    }
  }

  // 2. If doc.fields was empty, dynamically check common top-level properties
  if (fields.length === 0) {
    const candidateKeys = [
      'vendor_name',
      'invoice_number',
      'total_amount',
      'invoice_date',
      'student_name',
      'roll_number',
      'customer_name',
      'account_number',
      'tax_amount',
      'due_date',
    ];
    for (const k of candidateKeys) {
      if (doc[k] !== undefined && doc[k] !== null && String(doc[k]).trim() !== '') {
        const formattedKey = k
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());
        fields.push({
          key: k,
          label: formattedKey,
          value: String(doc[k]),
        });
      }
    }
  }

  return fields;
}

/**
 * Helper to dynamically extract all validation errors from a document
 */
function getDynamicErrors(doc) {
  const errors = [];

  if (Array.isArray(doc.validation_errors)) {
    doc.validation_errors.forEach((err) => {
      if (typeof err === 'string' && err.trim()) {
        errors.push(err);
      } else if (err && typeof err === 'object' && err.msg) {
        errors.push(err.msg);
      }
    });
  }

  // Check field-level validation errors
  if (doc.fields && typeof doc.fields === 'object') {
    for (const field of Object.values(doc.fields)) {
      if (field && Array.isArray(field.validation_errors)) {
        field.validation_errors.forEach((e) => {
          if (typeof e === 'string' && e.trim() && !errors.includes(e)) {
            errors.push(e);
          }
        });
      }
    }
  }

  if (doc.error_message && !errors.includes(doc.error_message)) {
    errors.push(doc.error_message);
  }

  return errors;
}

export default function ReviewQueueView({ onOpenVerify, onOpenView }) {
  const [reviewDocs, setReviewDocs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  const loadReviewQueue = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await fetchDocuments({
        page: 1,
        pageSize: 100,
        status: 'NEEDS_REVIEW',
      });
      setReviewDocs(data.items || []);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load review queue');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadReviewQueue();
  }, []);

  // Filter documents dynamically by search term
  const filteredDocs = useMemo(() => {
    if (!searchTerm.trim()) return reviewDocs;
    const query = searchTerm.toLowerCase();
    return reviewDocs.filter((doc) => {
      const idMatch = String(doc.id || doc.document_id).includes(query);
      const nameMatch = doc.file_name?.toLowerCase().includes(query);
      const typeMatch = doc.file_type?.toLowerCase().includes(query);
      return idMatch || nameMatch || typeMatch;
    });
  }, [reviewDocs, searchTerm]);

  const getFormatIcon = (fileType, fileName) => {
    const ext = (fileType || fileName?.split('.').pop() || '').toLowerCase();
    if (ext === 'pdf') return <FileText size={18} className="text-primary" />;
    if (['xlsx', 'xls', 'csv'].includes(ext)) return <FileSpreadsheet size={18} style={{ color: '#059669' }} />;
    if (['png', 'jpg', 'jpeg'].includes(ext)) return <ImageIcon size={18} style={{ color: '#8b5cf6' }} />;
    return <FileText size={18} className="text-primary" />;
  };

  const formatTimestamp = (ts) => {
    if (!ts) return null;
    try {
      const date = new Date(ts);
      if (isNaN(date.getTime())) return null;
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return null;
    }
  };

  return (
    <div className="review-queue-container" style={{ maxWidth: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* 1. Sleek, Minimal Control Header (No huge yellow banner) */}
      <div
        className="review-queue-toolbar"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '12px 18px',
          backgroundColor: '#ffffff',
          borderRadius: '10px',
          border: '1px solid var(--border-light, #e2e8f0)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              fontSize: '13px',
              fontWeight: '700',
              padding: '3px 10px',
              borderRadius: '20px',
              backgroundColor: '#fffbeb',
              color: '#b45309',
              border: '1px solid #fde68a',
            }}
          >
            {reviewDocs.length} Pending
          </span>
          <span style={{ fontSize: '13.5px', color: '#475569', fontWeight: '500' }}>
            Documents awaiting human verification & approval
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Quick Search */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#f8fafc',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              padding: '5px 10px',
            }}
          >
            <Search size={14} style={{ color: '#64748b' }} />
            <input
              type="text"
              placeholder="Filter by name or ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                border: 'none',
                background: 'transparent',
                outline: 'none',
                fontSize: '12.5px',
                width: '180px',
                color: '#1e293b',
              }}
            />
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadReviewQueue}
            title="Refresh Review Queue"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={13} className={isLoading ? 'spinning' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Review List */}
      <div className="review-cards-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {isLoading ? (
          <div
            style={{
              padding: '48px',
              textAlign: 'center',
              backgroundColor: '#ffffff',
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              color: '#64748b',
            }}
          >
            <RefreshCw size={18} className="spinning" />
            <span>Loading review queue items...</span>
          </div>
        ) : errorMsg ? (
          <div
            style={{
              padding: '16px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '10px',
              color: '#991b1b',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <AlertTriangle size={18} />
            <span>{errorMsg}</span>
          </div>
        ) : filteredDocs.length === 0 ? (
          <div
            style={{
              padding: '48px 24px',
              textAlign: 'center',
              backgroundColor: '#ffffff',
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
            }}
          >
            <CheckCircle2 size={44} style={{ color: '#10b981', margin: '0 auto 12px' }} />
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#1e293b', margin: '0 0 6px 0' }}>
              {searchTerm ? 'No matching documents found' : 'Review Queue is Clear!'}
            </h3>
            <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
              {searchTerm
                ? `No documents match "${searchTerm}". Try a different keyword.`
                : 'All documents have been verified and processed.'}
            </p>
          </div>
        ) : (
          filteredDocs.map((doc) => {
            const docId = doc.id || doc.document_id;
            const conf = doc.confidence ?? doc.confidence_score;
            const confPct = conf !== null && conf !== undefined ? Math.round(conf * 100) : null;
            const dynamicFields = getDynamicFields(doc);
            const dynamicErrors = getDynamicErrors(doc);
            const formattedTime = formatTimestamp(doc.uploaded_at || doc.updated_at);

            return (
              <div
                key={docId}
                className="review-item-card"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '20px',
                  backgroundColor: '#ffffff',
                  border: '1px solid var(--border-light, #e2e8f0)',
                  borderRadius: '10px',
                  padding: '14px 18px',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)',
                  transition: 'all 0.15s ease',
                }}
              >
                {/* Left Document Information & Dynamic Fields */}
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {/* Top Badges & Document Name */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {getFormatIcon(doc.file_type, doc.file_name)}
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: '700',
                        backgroundColor: '#f1f5f9',
                        color: '#475569',
                        padding: '2px 7px',
                        borderRadius: '4px',
                        textTransform: 'uppercase',
                      }}
                    >
                      {doc.file_type || doc.file_name?.split('.').pop() || 'FILE'}
                    </span>

                    <span style={{ fontSize: '11.5px', fontFamily: 'monospace', color: '#64748b', fontWeight: '600' }}>
                      #{docId}
                    </span>

                    {doc.document_type && (
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '600',
                          backgroundColor: '#eff6ff',
                          color: '#1d4ed8',
                          padding: '2px 7px',
                          borderRadius: '4px',
                          textTransform: 'capitalize',
                        }}
                      >
                        {doc.document_type.replace(/_/g, ' ')}
                      </span>
                    )}

                    {confPct !== null && (
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: '700',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          backgroundColor: confPct >= 85 ? '#ecfdf5' : '#fffbeb',
                          color: confPct >= 85 ? '#047857' : '#b45309',
                          border: `1px solid ${confPct >= 85 ? '#a7f3d0' : '#fde68a'}`,
                        }}
                      >
                        {confPct}% Confidence
                      </span>
                    )}

                    {formattedTime && (
                      <span style={{ fontSize: '11.5px', color: '#94a3b8', display: 'inline-flex', alignItems: 'center', gap: '4px', marginLeft: 'auto' }}>
                        <Clock size={12} />
                        <span>{formattedTime}</span>
                      </span>
                    )}
                  </div>

                  {/* Document Title */}
                  <h4
                    style={{
                      fontSize: '14.5px',
                      fontWeight: '700',
                      color: '#1e293b',
                      margin: 0,
                      cursor: 'pointer',
                    }}
                    onClick={() => onOpenVerify(docId)}
                    title={doc.file_name}
                  >
                    {doc.file_name}
                  </h4>

                  {/* Dynamic Extracted Fields Row (NEVER hardcoded) */}
                  {dynamicFields.length > 0 ? (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                      {dynamicFields.slice(0, 5).map((f) => (
                        <div
                          key={f.key}
                          style={{
                            fontSize: '11.5px',
                            backgroundColor: '#f8fafc',
                            border: '1px solid #e2e8f0',
                            borderRadius: '6px',
                            padding: '3px 8px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <span style={{ color: '#64748b', fontWeight: '600' }}>{f.label}:</span>
                          <span style={{ color: '#0f172a', fontWeight: '700' }}>{f.value}</span>
                        </div>
                      ))}
                      {dynamicFields.length > 5 && (
                        <span style={{ fontSize: '11px', color: '#64748b', fontWeight: '600' }}>
                          +{dynamicFields.length - 5} more
                        </span>
                      )}
                    </div>
                  ) : (
                    <div style={{ fontSize: '12px', color: '#94a3b8', fontStyle: 'italic' }}>
                      Pending field extraction &mdash; click Verify & Review to confirm fields.
                    </div>
                  )}

                  {/* Dynamic Validation Errors (Only if present) */}
                  {dynamicErrors.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                      {dynamicErrors.slice(0, 3).map((err, i) => (
                        <span
                          key={i}
                          style={{
                            fontSize: '11px',
                            fontWeight: '600',
                            color: '#b91c1c',
                            backgroundColor: '#fef2f2',
                            border: '1px solid #fecaca',
                            borderRadius: '4px',
                            padding: '2px 7px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <AlertTriangle size={11} />
                          <span>{err}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right Action: Single prominent "Verify & Review" button */}
                <div style={{ flexShrink: 0 }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onOpenVerify(docId)}
                    style={{
                      padding: '8px 16px',
                      fontSize: '13.5px',
                      fontWeight: '600',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      borderRadius: '7px',
                    }}
                  >
                    <CheckSquare size={15} />
                    <span>Verify & Review</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
