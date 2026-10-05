import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RefreshCw,
  X,
} from 'lucide-react';
import { uploadDocument } from '../services/api';

export default function UploadView({ onUploadComplete, onViewDocument }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successResult, setSuccessResult] = useState(null);
  const fileInputRef = useRef(null);

  const allowedExtensions = ['pdf', 'png', 'jpg', 'jpeg', 'csv', 'xlsx'];
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
    if (!allowedExtensions.includes(ext)) {
      setErrorMsg(`Unsupported file format (.${ext}). Allowed: PDF, PNG, JPG, CSV, XLSX.`);
      return;
    }

    setSelectedFile(file);
  };

  const handleUploadSubmit = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setErrorMsg(null);
    setSuccessResult(null);

    try {
      // Upload & execute automated extraction pipeline
      const uploadResp = await uploadDocument(selectedFile, false);
      const docId = uploadResp.id || uploadResp.document_id;
      const conf = uploadResp.overall_confidence ?? uploadResp.confidence_score;

      setSuccessResult({
        docId,
        fileName: selectedFile.name,
        status: uploadResp.status || 'VERIFIED',
        confidence: conf,
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

  const getFileIcon = (fileName) => {
    const ext = fileName?.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return <FileText size={28} className="text-primary" />;
    if (['xlsx', 'xls', 'csv'].includes(ext)) return <FileSpreadsheet size={28} style={{ color: '#059669' }} />;
    if (['png', 'jpg', 'jpeg'].includes(ext)) return <ImageIcon size={28} style={{ color: '#8b5cf6' }} />;
    return <FileText size={28} className="text-primary" />;
  };

  return (
    <div className="upload-view-wrapper" style={{ maxWidth: '680px', margin: '0 auto', padding: '16px 0 32px' }}>
      {/* 1. Header Card */}
      <div className="panel-card" style={{ marginBottom: '20px', padding: '24px 28px', borderRadius: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              backgroundColor: '#ebf3ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <UploadCloud size={26} className="text-primary" />
          </div>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#1e293b', margin: '0 0 4px 0' }}>
              Upload Document
            </h2>
            <p style={{ fontSize: '13.5px', color: '#64748b', margin: 0, lineHeight: 1.4 }}>
              Upload any document to automatically extract text, parse key fields, and verify data.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Success Alert Box */}
      {successResult && (
        <div
          className="panel-card"
          style={{
            marginBottom: '20px',
            padding: '20px 24px',
            borderRadius: '12px',
            border: '1px solid #a7f3d0',
            backgroundColor: '#ecfdf5',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
            <CheckCircle2 size={24} style={{ color: '#059669', flexShrink: 0, marginTop: '2px' }} />
            <div style={{ flex: 1 }}>
              <h4 style={{ margin: '0 0 4px 0', fontSize: '15px', fontWeight: '700', color: '#065f46' }}>
                Document Processed Successfully!
              </h4>
              <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#047857' }}>
                <strong>{successResult.fileName}</strong> (Doc #{successResult.docId}) has been ingested.
                {successResult.confidence !== null && successResult.confidence !== undefined && (
                  <span> &bull; Confidence: <strong>{Math.round(successResult.confidence * 100)}%</strong></span>
                )}
              </p>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                {onViewDocument && (
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => onViewDocument(successResult.docId)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    <span>View Document Details</span>
                    <ArrowRight size={14} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSuccessResult(null)}
                >
                  Upload Another File
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. Error Alert Box */}
      {errorMsg && (
        <div
          className="panel-card"
          style={{
            marginBottom: '20px',
            padding: '16px 20px',
            borderRadius: '12px',
            border: '1px solid #fecaca',
            backgroundColor: '#fef2f2',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <AlertCircle size={20} style={{ color: '#dc2626', flexShrink: 0 }} />
          <span style={{ fontSize: '13.5px', color: '#991b1b', flex: 1 }}>{errorMsg}</span>
          <button
            type="button"
            className="btn btn-icon btn-sm"
            onClick={() => setErrorMsg(null)}
            style={{ color: '#991b1b' }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* 4. Drag & Drop Upload Zone */}
      <div className="panel-card" style={{ padding: '28px', borderRadius: '12px' }}>
        <div
          className={`dropzone-box ${dragActive ? 'drag-active' : ''} ${selectedFile ? 'has-file' : ''}`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            padding: '36px 20px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx"
            onChange={handleFileInput}
            style={{ display: 'none' }}
          />

          <div className="dropzone-center">
            <div
              className="dropzone-cloud-icon"
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                backgroundColor: '#e8f0fe',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 12px',
              }}
            >
              <UploadCloud size={32} className="text-primary" />
            </div>

            <p style={{ fontSize: '15px', fontWeight: '600', color: '#1e293b', margin: '0 0 6px 0' }}>
              Drag and drop your document here, or <span style={{ color: '#1a56db', textDecoration: 'underline' }}>browse</span>
            </p>

            <p style={{ fontSize: '12.5px', color: '#64748b', margin: 0 }}>
              Supported formats: <strong>PDF, PNG, JPG, CSV, Excel</strong> (Up to 10 MB)
            </p>
          </div>
        </div>

        {/* Selected File Card */}
        {selectedFile && (
          <div
            style={{
              marginTop: '20px',
              padding: '14px 18px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {getFileIcon(selectedFile.name)}
              <div>
                <p style={{ margin: '0 0 2px 0', fontSize: '14px', fontWeight: '600', color: '#1e293b' }}>
                  {selectedFile.name}
                </p>
                <p style={{ margin: 0, fontSize: '12px', color: '#64748b', fontFamily: 'monospace' }}>
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
            >
              <X size={14} />
              <span>Remove</span>
            </button>
          </div>
        )}

        {/* Main Upload Submit Button */}
        <div style={{ marginTop: '24px' }}>
          <button
            type="button"
            className="btn btn-primary"
            style={{
              width: '100%',
              padding: '13px 20px',
              fontSize: '15px',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              borderRadius: '8px',
            }}
            disabled={!selectedFile || isUploading}
            onClick={handleUploadSubmit}
          >
            {isUploading ? (
              <>
                <RefreshCw size={18} className="spinning" />
                <span>Processing Document & Extracting Data...</span>
              </>
            ) : (
              <>
                <UploadCloud size={18} />
                <span>Upload & Process Document</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
