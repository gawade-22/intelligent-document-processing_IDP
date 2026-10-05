import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Image,
  CheckCircle2,
  AlertCircle,
  Play,
  Cpu,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { uploadDocument, processDocument } from '../services/api';
import { runAIExtraction } from '../api/ai';

export default function UploadView({ onUploadComplete, onViewDocument }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [autoProcess, setAutoProcess] = useState(true);
  const [extractionMethod, setExtractionMethod] = useState('rule_plus_llm');
  const [documentType, setDocumentType] = useState('auto');
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successResult, setSuccessResult] = useState(null);
  const fileInputRef = useRef(null);

  const allowedTypes = [
    'application/pdf',
    'image/png',
    'image/jpeg',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ];
  const maxSizeBytes = 10 * 1024 * 1024; // 10 MB

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file) => {
    setErrorMsg(null);
    setSuccessResult(null);

    if (file.size > maxSizeBytes) {
      setErrorMsg('File exceeds the 10 MB maximum upload limit.');
      return;
    }
    if (file.size === 0) {
      setErrorMsg('Uploaded file is empty (0 bytes).');
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase();
    const validExts = ['pdf', 'png', 'jpg', 'jpeg', 'csv', 'xlsx'];
    if (!validExts.includes(ext) && !allowedTypes.includes(file.type)) {
      setErrorMsg(`Unsupported file format (.${ext}). Allowed: PDF, PNG, JPG, CSV, XLSX.`);
      return;
    }

    setSelectedFile(file);
  };

  const handleUploadSubmit = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setErrorMsg(null);

    try {
      // 1. Upload & Process via Universal Pipeline (synchronous when autoProcess is true)
      const uploadResp = await uploadDocument(selectedFile, !autoProcess);
      const docId = uploadResp.id || uploadResp.document_id;

      setSuccessResult({
        docId,
        fileName: selectedFile.name,
        status: uploadResp.status || 'UPLOADED',
        confidence: uploadResp.confidence_score,
      });

      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (onUploadComplete) onUploadComplete();
    } catch (err) {
      setErrorMsg(err.message || 'File upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
  };

  return (
    <div className="upload-view-container">
      {/* 1. Header Banner */}
      <div className="upload-header-card">
        <div className="upload-header-icon-box">
          <UploadCloud size={28} className="text-primary" />
        </div>
        <div className="upload-header-content">
          <h2 className="upload-view-title">Document Ingestion & Pipeline Ingest Studio</h2>
          <p className="upload-view-desc">
            Upload single or multi-page documents (PDF, Excel, CSV, Images) for automatic OCR, schema extraction, rule + AI reconciliation, and confidence routing.
          </p>
        </div>
      </div>

      {/* 2. Main Upload Studio Grid */}
      <div className="upload-studio-grid">
        {/* Left Column: Drag & Drop Zone */}
        <div className="panel-card flex-2">
          <div className="panel-card-header">
            <h3 className="panel-card-title">Upload File</h3>
            <span className="panel-card-sub">Drag and drop document or click to browse</span>
          </div>

          <div
            className={`dropzone-box ${dragActive ? 'drag-active' : ''} ${selectedFile ? 'has-file' : ''}`}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx"
              onChange={handleFileInput}
              style={{ display: 'none' }}
            />

            <div className="dropzone-center">
              <div className="dropzone-cloud-icon">
                <UploadCloud size={36} />
              </div>

              {selectedFile ? (
                <div className="selected-file-details">
                  <span className="selected-file-name">{selectedFile.name}</span>
                  <span className="selected-file-size font-mono">{formatFileSize(selectedFile.size)}</span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm mt-2"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                  >
                    Change File
                  </button>
                </div>
              ) : (
                <div className="dropzone-text-group">
                  <p className="dropzone-prompt">
                    <span className="dropzone-highlight">Click to browse</span> or drag and drop invoice here
                  </p>
                  <p className="dropzone-sub">
                    PDF, PNG, JPG, CSV, or XLSX (Maximum 10 MB per file)
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Error Message */}
          {errorMsg && (
            <div className="alert-box alert-error mt-3">
              <AlertCircle size={16} />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Success Result Card */}
          {successResult && (
            <div className="alert-box alert-success mt-3">
              <CheckCircle2 size={18} className="text-green" />
              <div className="alert-success-text">
                <p className="font-semibold">
                  Document #{successResult.docId} ({successResult.fileName}) ingested successfully!
                </p>
                <p className="text-xs text-muted">
                  Status: <strong className="text-main">{successResult.status}</strong>
                  {successResult.confidence && ` | Extraction Confidence: ${Math.round(successResult.confidence * 100)}%`}
                </p>
              </div>
            </div>
          )}

          {/* Document Type Selector */}
          <div className="upload-options-card mt-3">
            <span className="options-section-label">Target Document Category:</span>
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              className="settings-input"
              style={{ width: '100%', padding: '8px 12px', fontSize: '13px', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '6px', background: '#fff' }}
            >
              <option value="auto">✨ Auto-Detect Type</option>
              <option value="invoice">📄 Invoice</option>
              <option value="purchase_order">📑 Purchase Order</option>
              <option value="receipt">🧾 Receipt</option>
              <option value="bank_statement">🏦 Bank Statement</option>
              <option value="resume">👤 Resume / CV</option>
              <option value="certificate">🎓 Certificate</option>
              <option value="contract">⚖️ Contract / Agreement</option>
              <option value="delivery_challan">🚚 Delivery Challan</option>
              <option value="medical_report">🩺 Medical Report</option>
              <option value="insurance">🛡️ Insurance Document</option>
              <option value="id_document">🪪 ID Document</option>
              <option value="expense_report">💳 Expense Report</option>
              <option value="application_form">📝 Application / Form</option>
            </select>
          </div>

          {/* Extraction Method Selector */}
          <div className="upload-options-card mt-4">
            <span className="options-section-label">Extraction Method:</span>
            <div className="extraction-method-radios">
              <label className={`method-radio-card ${extractionMethod === 'rule' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_method"
                  value="rule"
                  checked={extractionMethod === 'rule'}
                  onChange={() => setExtractionMethod('rule')}
                />
                <div className="radio-content">
                  <span className="radio-title">Rule-Based</span>
                  <span className="radio-sub">Deterministic regex & structural parsers</span>
                </div>
              </label>

              <label className={`method-radio-card ${extractionMethod === 'llm' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_method"
                  value="llm"
                  checked={extractionMethod === 'llm'}
                  onChange={() => setExtractionMethod('llm')}
                />
                <div className="radio-content">
                  <span className="radio-title">LLM Only</span>
                  <span className="radio-sub">Zero-shot generative document intelligence</span>
                </div>
              </label>

              <label className={`method-radio-card ${extractionMethod === 'rule_plus_llm' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_method"
                  value="rule_plus_llm"
                  checked={extractionMethod === 'rule_plus_llm'}
                  onChange={() => setExtractionMethod('rule_plus_llm')}
                />
                <div className="radio-content">
                  <span className="radio-title">
                    Rule + LLM <span className="recommended-tag">Default</span>
                  </span>
                  <span className="radio-sub">Multi-engine candidate extraction & reconciliation</span>
                </div>
              </label>
            </div>
          </div>

          {/* Pipeline Options */}
          <div className="upload-options-card mt-3">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={autoProcess}
                onChange={(e) => setAutoProcess(e.target.checked)}
                className="table-checkbox"
              />
              <div className="checkbox-text-group">
                <span className="checkbox-title">Execute AI/OCR Extraction Pipeline Immediately</span>
                <span className="checkbox-desc">
                  Runs text parsing, OCR fallback, AI prompt reconciliation, and confidence routing automatically upon upload.
                </span>
              </div>
            </label>
          </div>

          {/* Action Footer */}
          <div className="upload-action-footer mt-4">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={!selectedFile || isUploading}
              onClick={handleUploadSubmit}
            >
              {isUploading ? (
                <>
                  <span className="spinner-ring sm" />
                  <span>Processing Ingestion Pipeline...</span>
                </>
              ) : (
                <>
                  <UploadCloud size={18} />
                  <span>Upload & Ingest Document</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Ingestion Specifications & Format Support */}
        <div className="panel-card flex-1">
          <div className="panel-card-header">
            <h3 className="panel-card-title">Supported Ingestion Engines</h3>
            <span className="panel-card-sub">Automatic format detection & signature inspection</span>
          </div>

          <div className="specs-list">
            <div className="spec-item">
              <div className="spec-icon-box pdf">
                <FileText size={18} />
              </div>
              <div className="spec-details">
                <span className="spec-title">Digital & Scanned PDF</span>
                <span className="spec-desc">Native text stream extraction with automatic Tesseract OCR fallback for scanned pages.</span>
              </div>
            </div>

            <div className="spec-item">
              <div className="spec-icon-box excel">
                <FileSpreadsheet size={18} />
              </div>
              <div className="spec-details">
                <span className="spec-title">Excel (.xlsx, .xls)</span>
                <span className="spec-desc">Workbook tabular parsing with multi-sheet detection and row normalization.</span>
              </div>
            </div>

            <div className="spec-item">
              <div className="spec-icon-box csv">
                <FileText size={18} />
              </div>
              <div className="spec-details">
                <span className="spec-title">Delimited CSV</span>
                <span className="spec-desc">Comma/semicolon delimited records with automatic column header mapping.</span>
              </div>
            </div>

            <div className="spec-item">
              <div className="spec-icon-box image">
                <Image size={18} />
              </div>
              <div className="spec-details">
                <span className="spec-title">Image Invoices (.png, .jpg)</span>
                <span className="spec-desc">High-resolution image preprocessing, contrast enhancement, and bounding-box OCR.</span>
              </div>
            </div>
          </div>

          <div className="security-notice-box mt-4">
            <ShieldCheck size={18} className="text-primary flex-shrink-0" />
            <span className="security-notice-text">
              All uploads are sanitized, protected against path traversal, validated against binary magic bytes, and logged into the compliance audit trail.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
