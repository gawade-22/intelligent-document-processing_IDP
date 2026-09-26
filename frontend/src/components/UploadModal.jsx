import React, { useState, useRef } from 'react';
import {
  Upload,
  X,
  FileText,
  AlertCircle,
  CheckCircle2,
  Play,
  Cpu,
} from 'lucide-react';
import { uploadDocument, processDocument } from '../services/api';
import { runAIExtraction } from '../api/ai';

export default function UploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isProcessingImmediately, setIsProcessingImmediately] = useState(true);
  const [extractionMethod, setExtractionMethod] = useState('rule_plus_llm');
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const allowedTypes = [
    'application/pdf',
    'image/png',
    'image/jpeg',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ];
  const maxSizeBytes = 10 * 1024 * 1024; // 10 MB

  const handleFileDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file) => {
    setErrorMsg(null);
    setSuccessMsg(null);

    if (file.size > maxSizeBytes) {
      setErrorMsg('File size exceeds the 10 MB limit.');
      return;
    }

    if (file.size === 0) {
      setErrorMsg('Uploaded file is empty (0 bytes).');
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase();
    const validExts = ['pdf', 'png', 'jpg', 'jpeg', 'csv', 'xlsx'];
    if (!validExts.includes(ext)) {
      setErrorMsg('Unsupported file type. Please upload PDF, PNG, JPG, CSV, or XLSX.');
      return;
    }

    setSelectedFile(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg('Please select a file to upload.');
      return;
    }

    setIsUploading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      // 1. Upload to backend
      const uploadResult = await uploadDocument(selectedFile);
      const docId = uploadResult.id || uploadResult.document_id;

      // 2. Optionally trigger automated processing
      if (isProcessingImmediately && docId) {
        setSuccessMsg(`Document uploaded. Running AI processing pipeline (${extractionMethod}) for ID #${docId}...`);
        try {
          await runAIExtraction(docId, extractionMethod);
          setSuccessMsg(`Document successfully uploaded and processed!`);
        } catch (procErr) {
          setSuccessMsg(`Uploaded successfully. Note: Automated pipeline encountered: ${procErr.message}`);
        }
      } else {
        setSuccessMsg(`Document #${docId} successfully uploaded to queue.`);
      }

      setTimeout(() => {
        onUploadSuccess();
        handleClose();
      }, 1200);
    } catch (err) {
      setErrorMsg(err.message || 'An unexpected error occurred during upload.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleClose = () => {
    setSelectedFile(null);
    setErrorMsg(null);
    setSuccessMsg(null);
    setIsUploading(false);
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={handleClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h2 className="modal-title">Upload Document</h2>
            <p className="modal-subtitle">
              Upload invoices, receipts, forms, or certificates for extraction
            </p>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={handleClose}
            aria-label="Close modal"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          {/* Dropzone */}
          <div
            className={`upload-dropzone ${selectedFile ? 'has-file' : ''}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx"
              style={{ display: 'none' }}
            />

            <div className="dropzone-icon-box">
              <Upload size={32} className="dropzone-icon" />
            </div>

            {selectedFile ? (
              <div className="selected-file-details">
                <FileText size={20} className="file-icon" />
                <span className="file-name">{selectedFile.name}</span>
                <span className="file-size">
                  ({(selectedFile.size / (1024 * 1024)).toFixed(2)} MB)
                </span>
              </div>
            ) : (
              <div className="dropzone-text">
                <p className="dropzone-primary">
                  <strong>Click to upload</strong> or drag and drop files here
                </p>
                <p className="dropzone-secondary">
                  PDF, Scanned Image (PNG, JPG), CSV, XLSX (Up to 10 MB)
                </p>
              </div>
            )}
          </div>

          {/* Extraction Method Selector */}
          <div className="upload-options" style={{ marginTop: '12px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary, #64748b)', display: 'block', marginBottom: '6px' }}>
              Extraction Method:
            </span>
            <div className="extraction-method-radios-modal" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '12px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 8px', border: '1px solid var(--border-color, #e2e8f0)', borderRadius: '6px', cursor: 'pointer', background: extractionMethod === 'rule' ? 'var(--bg-active, #f1f5f9)' : 'transparent' }}>
                <input
                  type="radio"
                  name="modal_extraction_method"
                  value="rule"
                  checked={extractionMethod === 'rule'}
                  onChange={() => setExtractionMethod('rule')}
                />
                <span>Rule-Based</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 8px', border: '1px solid var(--border-color, #e2e8f0)', borderRadius: '6px', cursor: 'pointer', background: extractionMethod === 'llm' ? 'var(--bg-active, #f1f5f9)' : 'transparent' }}>
                <input
                  type="radio"
                  name="modal_extraction_method"
                  value="llm"
                  checked={extractionMethod === 'llm'}
                  onChange={() => setExtractionMethod('llm')}
                />
                <span>LLM Only</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 8px', border: '1px solid var(--border-color, #e2e8f0)', borderRadius: '6px', cursor: 'pointer', background: extractionMethod === 'rule_plus_llm' ? 'var(--bg-active, #f1f5f9)' : 'transparent' }}>
                <input
                  type="radio"
                  name="modal_extraction_method"
                  value="rule_plus_llm"
                  checked={extractionMethod === 'rule_plus_llm'}
                  onChange={() => setExtractionMethod('rule_plus_llm')}
                />
                <span>Rule + LLM (Default)</span>
              </label>
            </div>
          </div>

          {/* Options */}
          <div className="upload-options">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={isProcessingImmediately}
                onChange={(e) => setIsProcessingImmediately(e.target.checked)}
                className="custom-checkbox"
              />
              <span className="checkbox-text">
                <strong>Run automated pipeline immediately</strong> (OCR, Rule & AI extraction, validation)
              </span>
            </label>
          </div>

          {/* Messages */}
          {errorMsg && (
            <div className="alert-box alert-error">
              <AlertCircle size={16} />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="alert-box alert-success">
              <CheckCircle2 size={16} />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Footer Actions */}
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleClose}
              disabled={isUploading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!selectedFile || isUploading}
            >
              {isUploading ? (
                <>
                  <span className="spinner-ring sm" />
                  <span>Uploading & Processing...</span>
                </>
              ) : (
                <>
                  <Upload size={16} />
                  <span>Upload Document</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
