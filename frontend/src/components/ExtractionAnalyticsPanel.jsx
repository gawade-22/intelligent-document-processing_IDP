import React, { useState } from 'react';
import {
  FileText,
  Zap,
  TrendingUp,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  BarChart3,
  Search,
  ScanText,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from 'lucide-react';

export default function ExtractionAnalyticsPanel({ stats = null, isLoading = false }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeSubTab, setActiveSubTab] = useState('fields'); // 'fields' | 'channels' | 'tiers'

  const analytics = stats?.extraction_analytics || null;
  const totalRecords = analytics?.total_records ?? stats?.total_processed ?? 0;
  const avgConf = analytics?.average_confidence ?? stats?.average_confidence ?? 0;
  const avgConfPercent = Math.round(avgConf * 100);
  const autoRate = analytics?.automation_rate ?? stats?.accuracy_rate ?? 0;

  const fields = analytics?.fields_breakdown || [
    { field_name: 'vendor_name', label: 'Vendor Name', detection_rate: 0, average_confidence: 0, detected_count: 0, sources: {} },
    { field_name: 'invoice_number', label: 'Invoice Number', detection_rate: 0, average_confidence: 0, detected_count: 0, sources: {} },
    { field_name: 'invoice_date', label: 'Invoice Date', detection_rate: 0, average_confidence: 0, detected_count: 0, sources: {} },
    { field_name: 'total_amount', label: 'Total Amount', detection_rate: 0, average_confidence: 0, detected_count: 0, sources: {} },
  ];

  const textSources = analytics?.text_sources || {};
  const tiers = analytics?.confidence_tiers || {
    high: stats?.total_verified ?? 0,
    medium: 0,
    low: stats?.total_needing_review ?? 0,
  };

  const getConfidenceColorClass = (val) => {
    if (val >= 0.85) return 'text-emerald-600 bg-emerald-50 border-emerald-200';
    if (val >= 0.70) return 'text-amber-600 bg-amber-50 border-amber-200';
    return 'text-rose-600 bg-rose-50 border-rose-200';
  };

  const getSourceBadge = (sources) => {
    if (!sources || Object.keys(sources).length === 0) return 'No Source';
    const primary = Object.entries(sources).sort((a, b) => b[1] - a[1])[0][0];
    const labels = {
      rule: 'Rule Anchor',
      positional: 'Spatial Coordinate',
      ai: 'AI Engine',
      ocr_image: 'Tesseract OCR',
      digital_pdf: 'Native PDF',
      tabular: 'Spreadsheet',
    };
    return labels[primary] || primary;
  };

  return (
    <div className="extraction-analytics-panel">
      {/* Panel Top Header Bar */}
      <div className="eap-header">
        <div className="eap-header-left">
          <div className="eap-icon-box">
            <ScanText size={20} className="eap-main-icon" />
          </div>
          <div>
            <div className="eap-title-row">
              <h2 className="eap-title">Files Extraction Record Analytics</h2>
              <span className="eap-badge-live">
                <span className="pulse-dot"></span> Live Reconciled Records
              </span>
            </div>
            <p className="eap-subtitle">
              Detailed field recognition accuracy, confidence scoring, and multi-engine telemetry across {totalRecords} extraction record{totalRecords === 1 ? '' : 's'}.
            </p>
          </div>
        </div>

        <div className="eap-header-actions">
          <div className="eap-subtab-pills">
            <button
              type="button"
              className={`eap-pill ${activeSubTab === 'fields' ? 'active' : ''}`}
              onClick={() => setActiveSubTab('fields')}
            >
              <BarChart3 size={13} />
              <span>Field Accuracy</span>
            </button>
            <button
              type="button"
              className={`eap-pill ${activeSubTab === 'channels' ? 'active' : ''}`}
              onClick={() => setActiveSubTab('channels')}
            >
              <Cpu size={13} />
              <span>Engine Sources</span>
            </button>
            <button
              type="button"
              className={`eap-pill ${activeSubTab === 'tiers' ? 'active' : ''}`}
              onClick={() => setActiveSubTab('tiers')}
            >
              <ShieldCheck size={13} />
              <span>Confidence Tiers</span>
            </button>
          </div>

          <button
            type="button"
            className="eap-toggle-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? 'Collapse Analytics' : 'Expand Analytics'}
            aria-label="Toggle analytics panel visibility"
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="eap-body">
          {/* Quick Stats Summary Ribbon */}
          <div className="eap-summary-ribbon">
            <div className="eap-summary-stat">
              <span className="stat-label">Total Extraction Records</span>
              <span className="stat-val">{totalRecords}</span>
              <span className="stat-note">Reconciled & indexed</span>
            </div>
            <div className="eap-summary-divider" />
            <div className="eap-summary-stat">
              <span className="stat-label">Average Confidence</span>
              <span className="stat-val text-blue">{avgConfPercent}%</span>
              <span className="stat-note">Target benchmark: &ge; 85%</span>
            </div>
            <div className="eap-summary-divider" />
            <div className="eap-summary-stat">
              <span className="stat-label">Automation Rate (STP)</span>
              <span className="stat-val text-green">{autoRate}%</span>
              <span className="stat-note">Directly verified</span>
            </div>
            <div className="eap-summary-divider" />
            <div className="eap-summary-stat">
              <span className="stat-label">Active OCR Engine</span>
              <span className="stat-val font-mono-sm">Tesseract v5.5</span>
              <span className="stat-note">Local binary in PATH</span>
            </div>
          </div>

          {/* SubTab 1: Fields Breakdown */}
          {activeSubTab === 'fields' && (
            <div className="eap-fields-grid">
              {fields.map((f) => {
                const confScore = Math.round(f.average_confidence * 100);
                const isHigh = f.average_confidence >= 0.85;
                const isDetected = f.detected_count > 0;

                return (
                  <div key={f.field_name} className="field-analytics-card">
                    <div className="fac-header">
                      <div className="fac-title-group">
                        <span className="fac-field-name">{f.label}</span>
                        <span className="fac-source-badge">{getSourceBadge(f.sources)}</span>
                      </div>
                      <span className={`fac-conf-pill ${isDetected ? (isHigh ? 'pill-high' : 'pill-med') : 'pill-low'}`}>
                        {isDetected ? `${confScore}% Conf.` : 'Not Extracted'}
                      </span>
                    </div>

                    <div className="fac-metric-row">
                      <div className="fac-detected-rate">
                        <span className="fac-rate-number">{f.detection_rate}%</span>
                        <span className="fac-rate-label">Recognition Rate</span>
                      </div>
                      <div className="fac-records-ratio">
                        {f.detected_count} / {f.total_evaluated || totalRecords || 1} records
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="fac-progress-track">
                      <div
                        className={`fac-progress-fill ${isHigh ? 'fill-green' : isDetected ? 'fill-blue' : 'fill-gray'}`}
                        style={{ width: `${Math.max(f.detection_rate, isDetected ? 10 : 0)}%` }}
                      />
                    </div>

                    <div className="fac-footer">
                      <span className="fac-footer-text">
                        {isDetected
                          ? `${f.detected_count} value${f.detected_count === 1 ? '' : 's'} extracted & validated`
                          : 'Awaiting documents containing this field'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* SubTab 2: Engine Sources Distribution */}
          {activeSubTab === 'channels' && (
            <div className="eap-channels-view">
              <div className="eap-channels-left">
                <h4 className="channels-title">Extraction Pipelines Utilization</h4>
                <p className="channels-desc">
                  Breakdown of ingestion and parsing technologies invoked during the extraction lifecycle:
                </p>

                <div className="channel-bars-list">
                  <div className="channel-item">
                    <div className="channel-label-row">
                      <span className="ch-name">
                        <FileText size={14} className="text-blue" />
                        Digital PDF Text Stream (pypdf)
                      </span>
                      <span className="ch-count">
                        {textSources.digital_pdf || 0} docs
                      </span>
                    </div>
                    <div className="channel-track">
                      <div
                        className="channel-fill bg-blue"
                        style={{ width: `${totalRecords > 0 ? ((textSources.digital_pdf || 0) / totalRecords) * 100 : 0}%` }}
                      />
                    </div>
                  </div>

                  <div className="channel-item">
                    <div className="channel-label-row">
                      <span className="ch-name">
                        <ScanText size={14} className="text-purple" />
                        Tesseract OCR Engine (Local v5.5)
                      </span>
                      <span className="ch-count">
                        {(textSources.ocr_image || 0) + (textSources.ocr_scanned_pdf || 0)} docs
                      </span>
                    </div>
                    <div className="channel-track">
                      <div
                        className="channel-fill bg-purple"
                        style={{ width: `${totalRecords > 0 ? (((textSources.ocr_image || 0) + (textSources.ocr_scanned_pdf || 0)) / totalRecords) * 100 : 0}%` }}
                      />
                    </div>
                  </div>

                  <div className="channel-item">
                    <div className="channel-label-row">
                      <span className="ch-name">
                        <Cpu size={14} className="text-amber" />
                        AI / LLM Reconciled Extraction
                      </span>
                      <span className="ch-count">
                        {textSources.ai || 0} docs
                      </span>
                    </div>
                    <div className="channel-track">
                      <div
                        className="channel-fill bg-amber"
                        style={{ width: `${totalRecords > 0 ? ((textSources.ai || 0) / totalRecords) * 100 : 0}%` }}
                      />
                    </div>
                  </div>

                  <div className="channel-item">
                    <div className="channel-label-row">
                      <span className="ch-name">
                        <Layers size={14} className="text-emerald" />
                        Structured Tabular (Excel / CSV)
                      </span>
                      <span className="ch-count">
                        {textSources.tabular || 0} docs
                      </span>
                    </div>
                    <div className="channel-track">
                      <div
                        className="channel-fill bg-emerald"
                        style={{ width: `${totalRecords > 0 ? ((textSources.tabular || 0) / totalRecords) * 100 : 0}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="eap-channels-right">
                <div className="engine-health-card">
                  <div className="eh-icon-row">
                    <Sparkles size={18} className="text-blue" />
                    <span className="eh-badge">Active Engine</span>
                  </div>
                  <h5 className="eh-title">Hybrid Reconciled IDP</h5>
                  <p className="eh-desc">
                    Combines deterministic spatial regex rules with Tesseract OCR word-level bounding boxes and optional LLM synthesis for resilient field extraction.
                  </p>
                  <div className="eh-specs">
                    <div className="eh-spec-row">
                      <span>OCR Engine:</span>
                      <strong>Tesseract OCR</strong>
                    </div>
                    <div className="eh-spec-row">
                      <span>Tesseract PSM:</span>
                      <strong>Mode 6 (Single Block)</strong>
                    </div>
                    <div className="eh-spec-row">
                      <span>Default Language:</span>
                      <strong>English (eng)</strong>
                    </div>
                    <div className="eh-spec-row">
                      <span>Database:</span>
                      <strong>PostgreSQL (Connected)</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SubTab 3: Confidence Tiers */}
          {activeSubTab === 'tiers' && (
            <div className="eap-tiers-view">
              <div className="tier-card tier-high">
                <div className="tier-header">
                  <CheckCircle2 size={18} className="text-green" />
                  <span className="tier-name">High Confidence Tier</span>
                  <span className="tier-badge">&ge; 85%</span>
                </div>
                <div className="tier-count">{tiers.high || 0}</div>
                <p className="tier-desc">
                  Documents where all extracted fields met high confidence thresholds and passed business rule validation.
                </p>
                <div className="tier-action-tag tag-verified">Auto-Verified</div>
              </div>

              <div className="tier-card tier-medium">
                <div className="tier-header">
                  <AlertTriangle size={18} className="text-amber" />
                  <span className="tier-name">Needs Human Review</span>
                  <span className="tier-badge">&lt; 85%</span>
                </div>
                <div className="tier-count">{tiers.low + (tiers.medium || 0) || (stats?.total_needing_review ?? 0)}</div>
                <p className="tier-desc">
                  Extracted fields flagged with lower confidence or missing required values, routed to HITL triage queue.
                </p>
                <div className="tier-action-tag tag-review">Review Queue</div>
              </div>

              <div className="tier-card tier-failed">
                <div className="tier-header">
                  <FileText size={18} className="text-muted" />
                  <span className="tier-name">Pipeline Failures</span>
                  <span className="tier-badge">Errors</span>
                </div>
                <div className="tier-count">{stats?.total_failed ?? 0}</div>
                <p className="tier-desc">
                  Corrupted, empty, or unreadable files blocked during ingestion or binary validation stages.
                </p>
                <div className="tier-action-tag tag-failed">Error Handled</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
