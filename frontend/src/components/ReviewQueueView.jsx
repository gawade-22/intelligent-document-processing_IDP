import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  CheckSquare,
  RefreshCw,
  FileText,
  ArrowRight,
  ShieldAlert,
  SlidersHorizontal,
} from 'lucide-react';
import { fetchDocuments } from '../services/api';

export default function ReviewQueueView({ onOpenVerify, onOpenView }) {
  const [reviewDocs, setReviewDocs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);

  const loadReviewQueue = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      // Fetch specifically documents with NEEDS_REVIEW status
      const data = await fetchDocuments({
        page: 1,
        pageSize: 50,
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

  return (
    <div className="review-queue-container">
      {/* 1. Review Queue Header Banner */}
      <div className="review-banner-card">
        <div className="banner-icon-circle">
          <ShieldAlert size={24} className="banner-icon" />
        </div>
        <div className="banner-content">
          <h2 className="banner-title">Human-in-the-Loop (HITL) Verification Triage</h2>
          <p className="banner-desc">
            Documents routed here have failed automatic validation rules or fallen below the confidence threshold ({`85%`}). Review extracted fields against the original document to approve or correct records.
          </p>
        </div>
        <div className="banner-stats">
          <div className="queue-count-badge">
            <span className="queue-count-number">{reviewDocs.length}</span>
            <span className="queue-count-label">Awaiting Review</span>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadReviewQueue}
            title="Refresh Queue"
          >
            <RefreshCw size={14} className={isLoading ? 'spinning' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Review List */}
      <div className="review-cards-list">
        {isLoading ? (
          <div className="loading-card">
            <span className="spinner-ring" />
            <span>Loading review queue items...</span>
          </div>
        ) : errorMsg ? (
          <div className="alert-box alert-error">
            <AlertTriangle size={16} />
            <span>{errorMsg}</span>
          </div>
        ) : reviewDocs.length === 0 ? (
          <div className="empty-queue-card">
            <CheckCircle2 size={44} className="queue-clean-icon" />
            <h3>Review Queue is Clear!</h3>
            <p>All processed documents have met the 85% confidence threshold and validation rules.</p>
          </div>
        ) : (
          reviewDocs.map((doc) => {
            const conf = doc.confidence ?? doc.confidence_score;
            const confPct = conf !== null && conf !== undefined ? Math.round(conf * 100) : null;
            const fields = doc.fields || {};

            return (
              <div key={doc.id} className="review-item-card">
                <div className="review-item-main">
                  <div className="review-doc-header">
                    <div className="doc-badge-row">
                      <span className="file-type-pill">{doc.file_type || 'PDF'}</span>
                      <span className="doc-id-pill">ID #{doc.id}</span>
                      {confPct !== null && (
                        <span className={`conf-status-pill ${confPct < 85 ? 'low' : 'ok'}`}>
                          Confidence: {confPct}%
                        </span>
                      )}
                    </div>
                    <h3 className="review-doc-name">{doc.file_name}</h3>
                  </div>

                  {/* Summary of Key Fields */}
                  <div className="review-fields-summary">
                    <div className="summary-field">
                      <span className="f-label">Vendor:</span>
                      <span className="f-val">{doc.vendor_name || '— (Missing)'}</span>
                    </div>
                    <div className="summary-field">
                      <span className="f-label">Invoice No:</span>
                      <span className="f-val">{doc.invoice_number || '—'}</span>
                    </div>
                    <div className="summary-field">
                      <span className="f-label">Total Amount:</span>
                      <span className="f-val">{doc.total_amount ? `₹${doc.total_amount}` : '—'}</span>
                    </div>
                    <div className="summary-field">
                      <span className="f-label">Date:</span>
                      <span className="f-val">{doc.invoice_date || '—'}</span>
                    </div>
                  </div>

                  {/* Validation Flag notice */}
                  <div className="review-notice-banner">
                    <AlertTriangle size={14} className="notice-icon" />
                    <span>
                      {doc.error_message ||
                        (confPct && confPct < 85
                          ? `Overall confidence (${confPct}%) is below 85% requirement.`
                          : 'Validation requires human confirmation for missing or ambiguous fields.')}
                    </span>
                  </div>
                </div>

                {/* Right Action buttons */}
                <div className="review-item-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onOpenVerify(doc)}
                  >
                    <CheckSquare size={16} />
                    <span>Verify & Correct</span>
                    <ArrowRight size={14} />
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onOpenView(doc)}
                  >
                    <Eye size={14} />
                    <span>Inspect Raw Data</span>
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
