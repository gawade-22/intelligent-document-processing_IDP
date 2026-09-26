import React, { useState, useEffect } from 'react';
import {
  X,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ExternalLink,
  Save,
  Plus,
  RefreshCw,
  Download,
  Shield,
  Layers,
} from 'lucide-react';
import {
  fetchDocumentDetails,
  verifyDocument,
  processDocument,
  getDocumentFileUrl,
} from '../services/api';

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

  useEffect(() => {
    if (isOpen && docId) {
      loadDetails();
    } else {
      setDocDetails(null);
      setEditedFields({});
      setMessage(null);
      setErrorMsg(null);
    }
  }, [isOpen, docId]);

  const loadDetails = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await fetchDocumentDetails(docId);
      setDocDetails(data);

      // Pre-fill editable fields
      const initialFields = {};
      if (data.fields) {
        Object.entries(data.fields).forEach(([key, fieldObj]) => {
          initialFields[key] =
            fieldObj.normalized_value !== null && fieldObj.normalized_value !== undefined
              ? fieldObj.normalized_value
              : fieldObj.value ?? '';
        });
      }
      setEditedFields(initialFields);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load document details');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen || !docId) return null;

  const handleFieldChange = (key, val) => {
    setEditedFields((prev) => ({
      ...prev,
      [key]: val,
    }));
  };

  const handleAddNewField = (e) => {
    e.preventDefault();
    if (!newFieldName.trim()) return;

    setEditedFields((prev) => ({
      ...prev,
      [newFieldName.trim()]: newFieldValue,
    }));
    setNewFieldName('');
    setNewFieldValue('');
  };

  const handleSaveVerification = async () => {
    setIsSaving(true);
    setMessage(null);
    setErrorMsg(null);

    try {
      const result = await verifyDocument(docId, editedFields);
      setMessage(result.message || 'Corrections saved and re-validated successfully.');
      onUpdateSuccess();
      // Reload details to show updated validation state & confidence
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
      onUpdateSuccess();
      await loadDetails();
    } catch (err) {
      setErrorMsg(err.message || 'Pipeline execution failed');
    } finally {
      setIsProcessing(false);
    }
  };

  const fileUrl = getDocumentFileUrl(docId);
  const isPdf = docDetails?.file_type?.toUpperCase() === 'PDF' || docDetails?.file_name?.toLowerCase().endsWith('.pdf');
  const isImage = ['PNG', 'JPG', 'JPEG'].includes(docDetails?.file_type?.toUpperCase()) || /\.(png|jpg|jpeg)$/i.test(docDetails?.file_name || '');

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="viewer-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="viewer-modal-header">
          <div className="viewer-title-row">
            <FileText size={20} className="viewer-title-icon" />
            <h2 className="viewer-title">{docDetails?.file_name || `Document #${docId}`}</h2>
            <span className={`status-pill status-${docDetails?.status?.toLowerCase()}`}>
              {docDetails?.status}
            </span>
          </div>

          <div className="viewer-header-actions">
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
              <p>Loading document details and preview...</p>
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
                    <span className="panel-subtitle">Review confidence and submit corrections</span>
                  </div>

                  {docDetails?.confidence_score !== null && docDetails?.confidence_score !== undefined && (
                    <div className="overall-score-badge">
                      <span>Overall: </span>
                      <strong>{Math.round(docDetails.confidence_score * 100)}%</strong>
                    </div>
                  )}
                </div>

                {/* Status messages */}
                {message && (
                  <div className="alert-box alert-success sm">
                    <CheckCircle2 size={15} />
                    <span>{message}</span>
                  </div>
                )}
                {errorMsg && (
                  <div className="alert-box alert-error sm">
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

                {/* Editable Fields List */}
                <div className="fields-list-scroll">
                  {Object.entries(editedFields).map(([key, val]) => {
                    const meta = docDetails?.fields?.[key] || {};
                    const conf = meta.confidence;
                    const source = meta.source;

                    return (
                      <div key={key} className="field-edit-row">
                        <div className="field-meta-bar">
                          <label className="field-label-text">{key.replace(/_/g, ' ')}</label>
                          <div className="field-tags">
                            {source && (
                              <span className={`source-tag tag-${source.toLowerCase()}`}>
                                {source}
                              </span>
                            )}
                            {conf !== null && conf !== undefined && (
                              <span className="conf-tag">
                                {Math.round(conf * 100)}%
                              </span>
                            )}
                          </div>
                        </div>

                        <input
                          type="text"
                          className="field-text-input"
                          value={val || ''}
                          placeholder={`Enter ${key}...`}
                          onChange={(e) => handleFieldChange(key, e.target.value)}
                        />
                      </div>
                    );
                  })}

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
