import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  FileText,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  Table as TableIcon,
  Sliders,
  Layers,
  FileCode,
  Download,
  Check,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';
import EvidenceViewer from './EvidenceViewer';
import DynamicSections from './DynamicSections';
import DynamicTables from './DynamicTables';
import RunComparisonModal from './RunComparisonModal';
import {
  fetchDocumentV2,
  fetchDocumentExtractionV2,
  fetchDocumentStructureV2,
  fetchDocumentInsightsV2,
  updateFieldV2,
  createFieldV2,
  verifyDocumentV2,
  reprocessDocumentV2,
  downloadDocumentPdfReportV2,
} from '../../services/api';
import './dynamicStyles.css';

export default function UniversalDocumentViewer({
  docId,
  isOpen = true,
  onClose,
  onDocumentUpdated,
}) {
  const [docData, setDocData] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [structure, setStructure] = useState(null);
  const [insights, setInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeField, setActiveField] = useState(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [isDownloadingReport, setIsDownloadingReport] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);
  const [isComparisonOpen, setIsComparisonOpen] = useState(false);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const handleDownloadPdfReport = async () => {
    try {
      setIsDownloadingReport(true);
      const safeName = (docData?.file_name || 'document').replace(/\.[^/.]+$/, '');
      const filename = `${safeName}_extracted_report.pdf`;
      await downloadDocumentPdfReportV2(docId, filename);
      showToast('PDF report downloaded successfully.');
    } catch (err) {
      console.error('Failed to download PDF report:', err);
      showToast('Failed to download PDF report.');
    } finally {
      setIsDownloadingReport(false);
    }
  };

  const loadAllDocumentData = useCallback(async () => {
    if (!docId) return;
    setIsLoading(true);

    try {
      // 1. Fetch document base info
      const doc = await fetchDocumentV2(docId);
      setDocData(doc);

      // 2. Fetch UniversalExtractionResult contract
      try {
        const ext = await fetchDocumentExtractionV2(docId);
        setExtraction(ext);
        // Pre-select first field for evidence view
        if (ext?.fields?.length > 0 && !activeField) {
          setActiveField(ext.fields[0]);
        }
      } catch (e) {
        console.warn('Extraction not available yet:', e);
      }

      // 3. Fetch physical structure
      try {
        const struct = await fetchDocumentStructureV2(docId);
        setStructure(struct);
      } catch (e) {
        console.warn('Structure not available:', e);
      }

      // 4. Fetch dynamic insights
      try {
        const ins = await fetchDocumentInsightsV2(docId);
        setInsights(ins);
      } catch (e) {
        console.warn('Insights not available:', e);
      }
    } catch (err) {
      console.error('Failed to load v2 document:', err);
    } finally {
      setIsLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (isOpen && docId) {
      loadAllDocumentData();
    }
  }, [isOpen, docId, loadAllDocumentData]);

  if (!isOpen) return null;

  // Handle single field correction
  const handleUpdateField = async (fieldId, newValue) => {
    try {
      const res = await updateFieldV2(docId, fieldId, newValue);
      showToast('Field corrected and re-normalized.');

      // Update in-memory extraction fields
      setExtraction((prev) => {
        if (!prev) return prev;
        const updatedFields = (prev.fields || []).map((f) => {
          if (f.id === fieldId || f.key === res.canonical_key) {
            return {
              ...f,
              value: res.raw_value,
              normalized_value: res.normalized_value,
              status: res.status,
              confidence: res.confidence,
            };
          }
          return f;
        });
        return { ...prev, fields: updatedFields };
      });

      if (onDocumentUpdated) onDocumentUpdated();
    } catch (err) {
      console.error('Field update failed:', err);
      showToast('Failed to update field.');
    }
  };

  // Handle manual addition of custom field
  const handleCreateField = async (newFieldData) => {
    try {
      const created = await createFieldV2(docId, newFieldData);
      showToast(`Field "${created.label}" added successfully.`);

      // Update in-memory extraction fields
      setExtraction((prev) => {
        if (!prev) return prev;
        const currentFields = prev.fields || [];
        const newFieldItem = {
          id: created.id || `fld_custom_${created.field_id}`,
          key: created.canonical_key || created.key,
          label: created.label,
          section: created.section || 'Custom Fields',
          value: created.value,
          normalized_value: created.normalized_value,
          data_type: created.data_type || 'string',
          confidence: created.confidence || 1.0,
          status: created.status || 'edited',
          evidence: {
            page: 1,
            quote: created.value,
            bbox: [0, 0, 0, 0],
            grounded: true,
          },
          passes: [],
          editable: true,
        };
        return {
          ...prev,
          fields: [...currentFields, newFieldItem],
        };
      });

      if (onDocumentUpdated) onDocumentUpdated();
    } catch (err) {
      console.error('Failed to create custom field:', err);
      showToast('Failed to add field.');
    }
  };

  // Handle document verification
  const handleVerifyDocument = async () => {
    setIsVerifying(true);
    try {
      await verifyDocumentV2(docId);
      showToast('Document approved and marked as VERIFIED.');
      setDocData((prev) => (prev ? { ...prev, status: 'VERIFIED' } : prev));
      setExtraction((prev) => (prev ? { ...prev, status: 'VERIFIED' } : prev));
      if (onDocumentUpdated) onDocumentUpdated();
    } catch (err) {
      console.error('Verification failed:', err);
      showToast('Verification failed.');
    } finally {
      setIsVerifying(false);
    }
  };

  // Handle document reprocessing
  const handleReprocessDocument = async () => {
    setIsReprocessing(true);
    try {
      await reprocessDocumentV2(docId);
      showToast('Reprocessing queued. Refreshing data...');
      setTimeout(() => {
        loadAllDocumentData();
        if (onDocumentUpdated) onDocumentUpdated();
      }, 2000);
    } catch (err) {
      console.error('Reprocess failed:', err);
      showToast('Failed to reprocess document.');
    } finally {
      setIsReprocessing(false);
    }
  };

  const fields = extraction?.fields || [];
  const tables = extraction?.tables || [];
  const classification = extraction?.classification || {};
  const schemaInfo = extraction?.schema_info || {};
  const reviewFieldsCount = fields.filter(
    (f) => f.status === 'needs_review' || !f.evidence?.grounded || (f.confidence || 0) < 0.85
  ).length;

  const docConfidence =
    extraction?.doc_confidence ??
    extraction?.run?.doc_confidence ??
    docData?.latest_run?.metrics?.doc_confidence ??
    (fields.length > 0 ? fields.reduce((acc, f) => acc + (f.confidence || 0.9), 0) / fields.length : undefined);
  const confDisplay = docConfidence !== undefined ? `${Math.round(docConfidence * 100)}%` : '—';
  const isVerified = docData?.status === 'VERIFIED';

  return (
    <div className="universal-viewer-overlay" onClick={onClose}>
      <div
        className="universal-viewer-container"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <header className="uv-header">
          <div className="uv-header-left">
            <div className="uv-doc-icon-wrapper">
              <FileText size={22} />
            </div>

            <div className="uv-title-group">
              <div className="uv-title-row">
                <h2 className="uv-doc-title" title={docData?.file_name}>
                  {docData?.file_name || 'Document Processing'}
                </h2>

                {/* Open-Label Dynamic Classification Badge */}
                <span className="uv-badge uv-badge-primary">
                  {classification.primary_type || 'Universal Document'}
                </span>

                {/* Status Badge */}
                {isVerified ? (
                  <span className="uv-badge uv-badge-verified">
                    <CheckCircle2 size={11} /> Verified
                  </span>
                ) : (
                  <span className="uv-badge uv-badge-review">
                    <AlertTriangle size={11} /> Needs Review
                  </span>
                )}
              </div>

              <div className="uv-meta-row">
                <span>
                  Confidence: <strong>{confDisplay}</strong>
                </span>
              </div>
            </div>
          </div>

          <div className="uv-header-actions">
            {toastMessage && (
              <span className="uv-toast-chip animate-pulse">
                {toastMessage}
              </span>
            )}

            <button
              type="button"
              className="uv-btn uv-btn-primary"
              onClick={handleDownloadPdfReport}
              disabled={isDownloadingReport}
              title="Download executive PDF extraction report"
            >
              <Download size={14} className={isDownloadingReport ? 'animate-bounce' : ''} />
              <span>{isDownloadingReport ? 'Generating PDF...' : 'Download PDF Report'}</span>
            </button>

            <button
              type="button"
              className="uv-btn uv-btn-secondary"
              onClick={handleReprocessDocument}
              disabled={isReprocessing}
              title="Re-run extraction pipeline"
            >
              <RefreshCw size={14} className={isReprocessing ? 'animate-spin' : ''} />
              <span>{isReprocessing ? 'Reprocessing...' : 'Reprocess'}</span>
            </button>

            {!isVerified && (
              <button
                type="button"
                className="uv-btn uv-btn-success"
                onClick={handleVerifyDocument}
                disabled={isVerifying}
                title="Approve and mark document verified"
              >
                <CheckCircle2 size={14} />
                <span>{isVerifying ? 'Approving...' : 'Verify'}</span>
              </button>
            )}

            <button
              type="button"
              className="uv-btn-close"
              onClick={onClose}
              title="Close viewer"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Master Body: Split Pane */}
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center p-12 bg-white">
            <RefreshCw size={36} className="animate-spin text-blue-600 mb-3" />
            <h3 className="font-bold text-slate-800 text-base">Loading Universal Extraction</h3>
            <p className="text-xs text-slate-400 mt-1">
              Synchronizing physical structure, grounding evidence, and calibrated insights...
            </p>
          </div>
        ) : (
          <div className="uv-body">
            {/* Left Pane: Evidence Viewer */}
            <EvidenceViewer
              documentId={docId}
              fileType={docData?.file_type}
              activeField={activeField}
              structure={structure}
            />

            {/* Right Pane: Single Unified Extracted Information View */}
            <div className="uv-right-pane">
              {/* Single View Header */}
              <div className="uv-pane-header">
                <div className="uv-pane-title-group">
                  <div className="uv-pane-icon-badge">
                    <FileText size={18} />
                  </div>
                  <div>
                    <h3 className="uv-pane-title">Extracted Information</h3>
                    <p className="uv-pane-subtitle">
                      {fields.length} fields extracted • {confDisplay} confidence
                    </p>
                  </div>
                </div>
              </div>

              {/* Single Scrollable Extracted Content */}
              <div className="uv-pane-content">
                {/* Dynamic Insights / Summary Card if present */}
                {insights && insights.length > 0 && (
                  <div className="uv-insights-banner">
                    <div className="uv-insights-banner-title">
                      <Sparkles size={14} className="text-blue-500" />
                      <span>Document Insights & Metadata</span>
                    </div>
                    <div className="uv-insights-grid">
                      {insights.map((ins, i) => (
                        <div key={i} className="uv-insight-chip">
                          <span className="uv-insight-chip-label">{ins.title || ins.category}</span>
                          <span className="uv-insight-chip-value" title={ins.display_value || ins.value}>
                            {ins.display_value || ins.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Extracted Fields by Section with Evidence Clicking & Inline Editing */}
                <DynamicSections
                  sections={schemaInfo.sections || []}
                  fields={fields}
                  activeFieldId={activeField?.id || activeField?.key}
                  onSelectEvidence={(f) => setActiveField(f)}
                  onUpdateField={handleUpdateField}
                  onAddField={handleCreateField}
                />

                {/* Extracted Tables if present */}
                {tables.length > 0 && (
                  <div className="uv-tables-section">
                    <div className="uv-tables-header">
                      <TableIcon size={14} className="text-slate-500" />
                      <span>Extracted Tables ({tables.length})</span>
                    </div>
                    <DynamicTables
                      tables={tables}
                      onSelectEvidence={(f) => setActiveField(f)}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {isComparisonOpen && (
        <RunComparisonModal
          documentId={docId}
          onClose={() => setIsComparisonOpen(false)}
        />
      )}
    </div>
  );
}
