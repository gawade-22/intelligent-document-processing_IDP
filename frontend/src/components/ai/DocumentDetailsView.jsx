import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  FileText,
  ArrowLeft,
  RefreshCw,
  Sparkles,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Download,
  Save,
  Plus,
  ShieldCheck,
  Clock,
  Layers,
  CheckSquare,
} from 'lucide-react';
import { getDocumentById, verifyDocument, getDocumentFileUrl } from '../../api/documents';
import { getDocumentExtraction, runAIExtraction } from '../../api/ai';
import ExtractionComparison from './ExtractionComparison';

export default function DocumentDetailsView({ docId: propDocId, onBack }) {
  const params = useParams();
  const navigate = useNavigate();
  const docId = propDocId || params.id;

  const [docDetails, setDocDetails] = useState(null);
  const [extractionData, setExtractionData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Tabs on right panel
  const [rightPanelTab, setRightPanelTab] = useState('extraction'); // 'extraction', 'validation', 'audit'

  // Processing state with step tracker
  const [isProcessingAI, setIsProcessingAI] = useState(false);
  const [processingStep, setProcessingStep] = useState(null);

  // HITL review & editing state
  const [isReviewMode, setIsReviewMode] = useState(false);
  const [editedFields, setEditedFields] = useState({});
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [isSavingVerification, setIsSavingVerification] = useState(false);

  // Load document and extraction breakdown
  const loadDocumentData = useCallback(async () => {
    if (!docId) return;
    setIsLoading(true);
    setErrorMsg(null);

    try {
      // 1. Fetch base document record
      const doc = await getDocumentById(docId);
      setDocDetails(doc);

      // 2. Fetch full multi-tier extraction breakdown
      try {
        const ext = await getDocumentExtraction(docId);
        setExtractionData(ext);

        // Pre-fill fields for HITL review
        const initial = {};
        if (ext.final_result) {
          Object.entries(ext.final_result).forEach(([k, v]) => {
            initial[k] = v ?? '';
          });
        }
        setEditedFields(initial);
      } catch (extErr) {
        console.warn('Extraction breakdown not yet available:', extErr);
      }
    } catch (err) {
      setErrorMsg(err.message || `Failed to load document #${docId}`);
    } finally {
      setIsLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadDocumentData();
  }, [loadDocumentData]);

  // Handle Process with AI with realistic stepped feedback
  const handleProcessWithAI = async (method = 'rule_plus_llm') => {
    setIsProcessingAI(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    const steps = [
      'Preparing document...',
      'Extracting text / OCR...',
      'Running rule extraction...',
      'Running LLM extraction...',
      'Reconciling results...',
      'Validating & scoring...',
    ];

    let stepIdx = 0;
    setProcessingStep(steps[0]);

    const interval = setInterval(() => {
      stepIdx += 1;
      if (stepIdx < steps.length) {
        setProcessingStep(steps[stepIdx]);
      }
    }, 700);

    try {
      const resp = await runAIExtraction(docId, method);
      clearInterval(interval);
      setProcessingStep('Complete');
      setSuccessMsg('AI Extraction & Reconciliation completed successfully!');
      await loadDocumentData();
    } catch (err) {
      clearInterval(interval);
      setErrorMsg(err.message || 'AI processing encountered an error.');
    } finally {
      setTimeout(() => {
        setIsProcessingAI(false);
        setProcessingStep(null);
      }, 900);
    }
  };

  // Handle field edit during review
  const handleFieldChange = (key, value) => {
    setEditedFields((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  // Add custom field
  const handleAddField = (e) => {
    e.preventDefault();
    if (!newFieldName.trim()) return;
    setEditedFields((prev) => ({
      ...prev,
      [newFieldName.trim()]: newFieldValue,
    }));
    setNewFieldName('');
    setNewFieldValue('');
  };

  // Submit HITL Verification
  const handleSaveVerification = async () => {
    setIsSavingVerification(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      await verifyDocument(docId, editedFields);
      setSuccessMsg('Human verification saved! Document updated to VERIFIED.');
      setIsReviewMode(false);
      await loadDocumentData();
    } catch (err) {
      setErrorMsg(err.message || 'Failed to save verification corrections.');
    } finally {
      setIsSavingVerification(false);
    }
  };

  const fileUrl = docId ? getDocumentFileUrl(docId) : '';
  const isPdf =
    docDetails?.file_type?.toUpperCase() === 'PDF' ||
    docDetails?.file_name?.toLowerCase().endsWith('.pdf');
  const isImage =
    ['PNG', 'JPG', 'JPEG'].includes(docDetails?.file_type?.toUpperCase()) ||
    /\.(png|jpg|jpeg)$/i.test(docDetails?.file_name || '');

  return (
    <div className="doc-details-page-container">
      {/* 1. Breadcrumbs & Header Bar */}
      <div className="doc-details-header-bar">
        <div className="details-header-left">
          <button
            type="button"
            className="btn btn-secondary btn-sm btn-back"
            onClick={onBack ? onBack : () => navigate('/documents')}
            title="Return to Documents Table"
          >
            <ArrowLeft size={14} />
            <span>Documents</span>
          </button>
          <div className="doc-breadcrumbs">
            <span className="crumb-segment">Documents</span>
            <span className="crumb-separator">/</span>
            <span className="crumb-active">{docDetails?.file_name || `Doc #${docId}`}</span>
          </div>
        </div>

        <div className="details-header-actions">
          {/* Process with AI Button */}
          <button
            type="button"
            className="btn btn-primary btn-ai-process"
            onClick={() => handleProcessWithAI('rule_plus_llm')}
            disabled={isProcessingAI}
            title="Execute Rule + LLM extraction pipeline"
          >
            {isProcessingAI ? (
              <RefreshCw size={15} className="spinning" />
            ) : (
              <Sparkles size={15} />
            )}
            <span>{isProcessingAI ? (processingStep || 'Processing...') : 'Process with AI'}</span>
          </button>

          {/* HITL Review Toggle Button */}
          {docDetails?.status === 'NEEDS_REVIEW' && !isReviewMode && (
            <button
              type="button"
              className="btn btn-warning"
              onClick={() => {
                setIsReviewMode(true);
                setRightPanelTab('extraction');
              }}
              title="Open Human-in-the-Loop review form"
            >
              <CheckSquare size={15} />
              <span>Review Document</span>
            </button>
          )}

          {/* Download Original File */}
          <a
            href={fileUrl}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary btn-sm"
            download
            title="Download document file"
          >
            <Download size={14} />
            <span>Download</span>
          </a>

          {/* Reload data */}
          <button
            type="button"
            className="btn btn-icon"
            onClick={loadDocumentData}
            title="Reload details"
          >
            <RefreshCw size={15} className={isLoading ? 'spinning' : ''} />
          </button>
        </div>
      </div>

      {/* Notifications */}
      {successMsg && (
        <div className="app-toast toast-success" style={{ margin: '0 0 16px 0' }}>
          <CheckCircle2 size={16} />
          <span>{successMsg}</span>
        </div>
      )}
      {errorMsg && (
        <div className="app-toast toast-error" style={{ margin: '0 0 16px 0' }}>
          <AlertTriangle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 2. Main Two-Panel Layout */}
      <div className="doc-two-panel-grid">
        {/* =========================================
            LEFT PANEL: ORIGINAL DOCUMENT VIEWER
           ========================================= */}
        <div className="doc-panel doc-viewer-panel">
          <div className="panel-inner-header">
            <div className="panel-title-with-icon">
              <FileText size={18} className="text-primary" />
              <h3 className="panel-heading">Original Document Viewer</h3>
            </div>
            <a
              href={fileUrl}
              target="_blank"
              rel="noreferrer"
              className="preview-tab-link"
              title="Open raw file in separate browser tab"
            >
              <span>Open in new tab</span>
              <ExternalLink size={13} />
            </a>
          </div>

          <div className="viewer-frame-container">
            {isLoading ? (
              <div className="viewer-loading-box">
                <span className="spinner-ring" />
                <p>Loading document preview...</p>
              </div>
            ) : isPdf ? (
              <iframe
                src={fileUrl}
                title={`PDF Viewer: ${docDetails?.file_name}`}
                className="pdf-viewer-frame"
              />
            ) : isImage ? (
              <div className="image-viewer-box">
                <img
                  src={fileUrl}
                  alt={`Preview: ${docDetails?.file_name}`}
                  className="image-viewer-element"
                />
              </div>
            ) : (
              <div className="structured-file-viewer-card">
                <FileText size={52} className="text-secondary" />
                <h4>Tabular / Data File ({docDetails?.file_type})</h4>
                <p>{docDetails?.file_name}</p>
                <a href={fileUrl} className="btn btn-primary btn-sm" download>
                  Download File to Inspect
                </a>
              </div>
            )}
          </div>

          {/* Document Metadata Footer */}
          <div className="viewer-meta-footer">
            <div className="meta-footer-item">
              <span className="meta-footer-label">File Type:</span>
              <span className="meta-footer-val">{docDetails?.file_type || 'Unknown'}</span>
            </div>
            <div className="meta-footer-item">
              <span className="meta-footer-label">Size:</span>
              <span className="meta-footer-val">
                {docDetails?.file_size
                  ? `${(docDetails.file_size / 1024).toFixed(1)} KB`
                  : '—'}
              </span>
            </div>
            <div className="meta-footer-item">
              <span className="meta-footer-label">Status:</span>
              <span className={`status-pill status-${docDetails?.status?.toLowerCase()}`}>
                {docDetails?.status}
              </span>
            </div>
          </div>
        </div>

        {/* =========================================
            RIGHT PANEL: AI EXTRACTION & RESULTS
           ========================================= */}
        <div className="doc-panel doc-extraction-panel">
          {/* Panel Top Navigation Tabs */}
          <div className="extraction-panel-nav">
            <button
              type="button"
              className={`panel-nav-btn ${rightPanelTab === 'extraction' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('extraction')}
            >
              <Sparkles size={15} />
              <span>Extraction & Comparison</span>
            </button>
            <button
              type="button"
              className={`panel-nav-btn ${rightPanelTab === 'validation' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('validation')}
            >
              <ShieldCheck size={15} />
              <span>Validation Rules</span>
              {extractionData?.validation_errors?.length > 0 && (
                <span className="panel-tab-badge alert">
                  {extractionData.validation_errors.length}
                </span>
              )}
            </button>
            <button
              type="button"
              className={`panel-nav-btn ${rightPanelTab === 'audit' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('audit')}
            >
              <Clock size={15} />
              <span>Audit History</span>
            </button>
          </div>

          <div className="panel-body-scrollable">
            {/* TAB 1: Extraction & Comparison */}
            {rightPanelTab === 'extraction' && (
              <div className="extraction-wrapper">
                {isReviewMode && (
                  <div className="hitl-banner">
                    <div className="hitl-banner-text">
                      <strong>Human-in-the-Loop Verification Active:</strong>
                      <p>
                        Edit fields directly in the table below or add missing key-value pairs.
                        Click Save Verification when complete.
                      </p>
                    </div>
                    <div className="hitl-banner-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setIsReviewMode(false)}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={handleSaveVerification}
                        disabled={isSavingVerification}
                      >
                        <Save size={14} />
                        <span>{isSavingVerification ? 'Saving...' : 'Save Verification'}</span>
                      </button>
                    </div>
                  </div>
                )}

                <ExtractionComparison
                  extractionData={extractionData}
                  isEditable={isReviewMode}
                  editedValues={editedFields}
                  onFieldEdit={handleFieldChange}
                />

                {/* HITL Add Field row when in review mode */}
                {isReviewMode && (
                  <form onSubmit={handleAddField} className="add-field-form">
                    <span className="add-field-label">Add Field:</span>
                    <input
                      type="text"
                      className="add-field-input"
                      placeholder="Field name (e.g. tax_id)"
                      value={newFieldName}
                      onChange={(e) => setNewFieldName(e.target.value)}
                    />
                    <input
                      type="text"
                      className="add-field-input"
                      placeholder="Field value"
                      value={newFieldValue}
                      onChange={(e) => setNewFieldValue(e.target.value)}
                    />
                    <button type="submit" className="btn btn-secondary btn-sm">
                      <Plus size={14} />
                      <span>Add</span>
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* TAB 2: Validation Rules */}
            {rightPanelTab === 'validation' && (
              <div className="validation-tab-content">
                <div className="validation-section-card">
                  <h4 className="validation-section-title">Automated Validation Status</h4>
                  {extractionData?.validation_errors?.length === 0 ? (
                    <div className="validation-clean-state">
                      <CheckCircle2 size={32} className="text-success" />
                      <div>
                        <strong>All Business Rules Passed</strong>
                        <p>No structural or arithmetic discrepancies detected.</p>
                      </div>
                    </div>
                  ) : (
                    <div className="validation-error-list">
                      {extractionData?.validation_errors?.map((err, i) => (
                        <div key={i} className="validation-error-item">
                          <AlertTriangle size={16} className="text-warning" />
                          <span>{err}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="validation-section-card mt-3">
                  <h4 className="validation-section-title">Routing Decision</h4>
                  <div className="routing-decision-row">
                    <span className="decision-label">Document Routing Status:</span>
                    <span className={`status-pill status-${docDetails?.status?.toLowerCase()}`}>
                      {docDetails?.status}
                    </span>
                  </div>
                  <p className="routing-desc">
                    {docDetails?.status === 'VERIFIED'
                      ? 'Confidence score and validation criteria satisfied automated approval thresholds.'
                      : 'Confidence score fell below 85% or extraction candidates presented discrepancies requiring validator confirmation.'}
                  </p>
                </div>
              </div>
            )}

            {/* TAB 3: Audit History */}
            {rightPanelTab === 'audit' && (
              <div className="audit-tab-content">
                <div className="audit-timeline">
                  <div className="timeline-item">
                    <div className="timeline-dot dot-info" />
                    <div className="timeline-content">
                      <div className="timeline-header">
                        <strong>Document Uploaded</strong>
                        <span className="timeline-time">
                          {docDetails?.uploaded_at
                            ? new Date(docDetails.uploaded_at).toLocaleString()
                            : '—'}
                        </span>
                      </div>
                      <p className="timeline-desc">
                        Ingested <code>{docDetails?.file_name}</code> (Format: {docDetails?.file_type}).
                      </p>
                    </div>
                  </div>

                  <div className="timeline-item">
                    <div className="timeline-dot dot-primary" />
                    <div className="timeline-content">
                      <div className="timeline-header">
                        <strong>Pipeline Processing</strong>
                        <span className="timeline-time">
                          {docDetails?.processed_at
                            ? new Date(docDetails.processed_at).toLocaleString()
                            : 'Completed'}
                        </span>
                      </div>
                      <p className="timeline-desc">
                        Executed extraction via method:{' '}
                        <strong>{extractionData?.extraction_method_used || 'rule+ai'}</strong>.
                        Confidence score:{' '}
                        {docDetails?.confidence_score !== null && docDetails?.confidence_score !== undefined
                          ? `${Math.round(docDetails.confidence_score * 100)}%`
                          : '—'}
                      </p>
                    </div>
                  </div>

                  {docDetails?.status === 'VERIFIED' && (
                    <div className="timeline-item">
                      <div className="timeline-dot dot-success" />
                      <div className="timeline-content">
                        <div className="timeline-header">
                          <strong>Verification Confirmed</strong>
                          <span className="timeline-time">
                            {docDetails?.updated_at
                              ? new Date(docDetails.updated_at).toLocaleString()
                              : 'Verified'}
                          </span>
                        </div>
                        <p className="timeline-desc">
                          Status marked <code>VERIFIED</code>. Ready for downstream ERP/accounting export.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
