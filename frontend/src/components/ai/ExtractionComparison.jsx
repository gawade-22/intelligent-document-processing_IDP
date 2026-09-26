import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  Layers,
  Sparkles,
  Cpu,
  GitCompare,
  HelpCircle,
  ShieldCheck,
  UserCheck,
  AlertCircle,
  FileText,
} from 'lucide-react';

export default function ExtractionComparison({
  extractionData,
  onFieldEdit,
  isEditable = false,
  editedValues = {},
}) {
  const [activeTab, setActiveTab] = useState('final');

  if (!extractionData) {
    return (
      <div className="empty-extraction-state">
        <FileText size={36} className="empty-icon" />
        <p>No extraction results available.</p>
        <span className="empty-sub">
          Run AI extraction or execute the processing pipeline to see field-level data.
        </span>
      </div>
    );
  }

  const {
    document_id,
    file_name,
    status,
    confidence_score,
    extraction_method_used = 'rule+ai',
    rule_extraction = {},
    llm_extraction = {},
    reconciliation = {},
    final_result = {},
    validation_errors = [],
    review_reasons = [],
  } = extractionData;

  // Collect all unique field keys across rule, llm, and final
  const allFieldKeys = Array.from(
    new Set([
      ...Object.keys(final_result || {}),
      ...Object.keys(reconciliation || {}),
      ...Object.keys(rule_extraction || {}),
      ...Object.keys(llm_extraction || {}),
    ])
  );

  // Confidence Tier helper
  const getConfidenceTier = (score) => {
    if (score === null || score === undefined) return { label: 'N/A', cls: 'conf-none' };
    const pct = Math.round(score * 100);
    if (pct >= 85) return { label: 'High', cls: 'conf-high', pct };
    if (pct >= 60) return { label: 'Medium', cls: 'conf-med', pct };
    return { label: 'Low', cls: 'conf-low', pct };
  };

  // Source Badge renderer
  const renderSourceBadge = (source) => {
    const s = (source || 'none').toLowerCase();
    if (s === 'rule+ai' || s === 'rule + ai') {
      return (
        <span className="badge-source badge-source-reconciled" title="Reconciled from Rule + AI agreement">
          <Sparkles size={11} />
          <span>RULE + AI</span>
        </span>
      );
    }
    if (s === 'ai' || s === 'llm') {
      return (
        <span className="badge-source badge-source-ai" title="Extracted by LLM engine">
          <Cpu size={11} />
          <span>AI</span>
        </span>
      );
    }
    if (s === 'rule' || s === 'regex') {
      return (
        <span className="badge-source badge-source-rule" title="Extracted by deterministic rule engine">
          <Layers size={11} />
          <span>RULE</span>
        </span>
      );
    }
    if (s === 'human' || s === 'user') {
      return (
        <span className="badge-source badge-source-human" title="Verified or adjusted by human reviewer">
          <UserCheck size={11} />
          <span>HUMAN</span>
        </span>
      );
    }
    return (
      <span className="badge-source badge-source-none">
        <span>NONE</span>
      </span>
    );
  };

  // Comparison status badge renderer
  const renderComparisonStatusBadge = (statusStr) => {
    const st = (statusStr || '').toUpperCase();
    if (st === 'AGREED') {
      return (
        <span className="status-badge-agreed">
          <CheckCircle2 size={12} />
          <span>AGREED</span>
        </span>
      );
    }
    if (st === 'REVIEW REQUIRED' || st === 'CONFLICT') {
      return (
        <span className="status-badge-review">
          <AlertTriangle size={12} />
          <span>REVIEW REQUIRED</span>
        </span>
      );
    }
    if (st === 'REFINED') {
      return (
        <span className="status-badge-refined">
          <Sparkles size={12} />
          <span>REFINED</span>
        </span>
      );
    }
    return (
      <span className="status-badge-single">
        <span>SINGLE SOURCE</span>
      </span>
    );
  };

  // Format field labels nicely
  const formatFieldLabel = (key) => {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  return (
    <div className="extraction-comparison-widget">
      {/* 1. Method & Overall Quality Header */}
      <div className="extraction-widget-meta-bar">
        <div className="meta-bar-item">
          <span className="meta-label">Extraction Method:</span>
          <span className="meta-value method-pill">{extraction_method_used}</span>
        </div>

        {confidence_score !== null && confidence_score !== undefined && (
          <div className="meta-bar-item">
            <span className="meta-label">Average Confidence:</span>
            <div className="confidence-pill-group">
              <div className="confidence-progress-track">
                <div
                  className={`confidence-progress-bar ${
                    confidence_score >= 0.85
                      ? 'bar-high'
                      : confidence_score >= 0.6
                      ? 'bar-med'
                      : 'bar-low'
                  }`}
                  style={{ width: `${Math.round(confidence_score * 100)}%` }}
                />
              </div>
              <strong className="confidence-pct">
                {Math.round(confidence_score * 100)}%
              </strong>
            </div>
          </div>
        )}

        <div className="meta-bar-item">
          <span className="meta-label">Routing Status:</span>
          <span className={`status-pill status-${status?.toLowerCase()}`}>
            {status}
          </span>
        </div>
      </div>

      {/* Validation or Fallback Alerts if any */}
      {validation_errors && validation_errors.length > 0 && (
        <div className="validation-alert-banner">
          <AlertTriangle size={16} />
          <div className="validation-alert-content">
            <strong>Validation Rule Warnings:</strong>
            <ul>
              {validation_errors.map((err, idx) => (
                <li key={idx}>{err}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* 2. Interactive Navigation Tabs */}
      <div className="extraction-tabs-header">
        <button
          type="button"
          className={`extraction-tab-btn ${activeTab === 'final' ? 'active' : ''}`}
          onClick={() => setActiveTab('final')}
        >
          <ShieldCheck size={14} />
          <span>Final Result</span>
        </button>

        <button
          type="button"
          className={`extraction-tab-btn ${activeTab === 'rule' ? 'active' : ''}`}
          onClick={() => setActiveTab('rule')}
        >
          <Layers size={14} />
          <span>Rule Extraction</span>
          {Object.keys(rule_extraction || {}).length > 0 && (
            <span className="tab-count-badge">{Object.keys(rule_extraction).length}</span>
          )}
        </button>

        <button
          type="button"
          className={`extraction-tab-btn ${activeTab === 'llm' ? 'active' : ''}`}
          onClick={() => setActiveTab('llm')}
        >
          <Cpu size={14} />
          <span>LLM Extraction</span>
          {Object.keys(llm_extraction || {}).length > 0 && (
            <span className="tab-count-badge">{Object.keys(llm_extraction).length}</span>
          )}
        </button>

        <button
          type="button"
          className={`extraction-tab-btn ${activeTab === 'comparison' ? 'active' : ''}`}
          onClick={() => setActiveTab('comparison')}
        >
          <GitCompare size={14} />
          <span>Comparison</span>
        </button>
      </div>

      {/* 3. Tab Contents */}
      <div className="extraction-tab-content-area">
        {/* A. FINAL RESULT TAB */}
        {activeTab === 'final' && (
          <div className="tab-panel">
            <div className="table-responsive-container">
              <table className="enterprise-data-table extraction-table">
                <thead>
                  <tr>
                    <th style={{ width: '25%' }}>Field</th>
                    <th style={{ width: '35%' }}>Extracted / Normalized Value</th>
                    <th style={{ width: '22%' }}>Confidence</th>
                    <th style={{ width: '18%' }}>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {allFieldKeys.map((key) => {
                    const reconDetail = reconciliation[key] || {};
                    const finalVal =
                      editedValues[key] !== undefined
                        ? editedValues[key]
                        : final_result[key] !== undefined
                        ? final_result[key]
                        : reconDetail.value;

                    const confObj = getConfidenceTier(reconDetail.confidence);
                    const source = reconDetail.source || 'none';

                    return (
                      <tr key={key}>
                        <td className="field-name-cell">
                          <strong>{formatFieldLabel(key)}</strong>
                          <span className="field-key-slug">{key}</span>
                        </td>
                        <td className="field-value-cell">
                          {isEditable ? (
                            <input
                              type="text"
                              className="field-inline-input"
                              value={finalVal ?? ''}
                              onChange={(e) => onFieldEdit && onFieldEdit(key, e.target.value)}
                            />
                          ) : (
                            <span className={finalVal ? 'value-present' : 'value-missing'}>
                              {finalVal !== null && finalVal !== undefined && finalVal !== ''
                                ? String(finalVal)
                                : '—'}
                            </span>
                          )}
                        </td>
                        <td className="field-confidence-cell">
                          <div className="confidence-cell-group">
                            <span className={`confidence-badge-pill ${confObj.cls}`}>
                              {confObj.pct !== undefined ? `${confObj.pct}%` : 'N/A'}
                            </span>
                            {confObj.pct !== undefined && (
                              <div className="confidence-mini-bar-track">
                                <div
                                  className={`confidence-mini-bar-fill ${confObj.cls}`}
                                  style={{ width: `${confObj.pct}%` }}
                                />
                              </div>
                            )}
                            <span className="confidence-level-tag">{confObj.label}</span>
                          </div>
                        </td>
                        <td className="field-source-cell">{renderSourceBadge(source)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* B. RULE EXTRACTION TAB */}
        {activeTab === 'rule' && (
          <div className="tab-panel">
            {Object.keys(rule_extraction || {}).length === 0 ? (
              <div className="empty-sub-state">
                <Layers size={28} />
                <p>No rule-based extraction candidates found for this document.</p>
              </div>
            ) : (
              <div className="table-responsive-container">
                <table className="enterprise-data-table extraction-table">
                  <thead>
                    <tr>
                      <th style={{ width: '30%' }}>Field</th>
                      <th style={{ width: '45%' }}>Rule Extracted Value</th>
                      <th style={{ width: '25%' }}>Rule Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(rule_extraction).map(([key, detail]) => {
                      const confObj = getConfidenceTier(detail.confidence);
                      return (
                        <tr key={key}>
                          <td className="field-name-cell">
                            <strong>{formatFieldLabel(key)}</strong>
                            <span className="field-key-slug">{key}</span>
                          </td>
                          <td className="field-value-cell">
                            <span className={detail.value ? 'value-present' : 'value-missing'}>
                              {detail.value !== null && detail.value !== undefined
                                ? String(detail.value)
                                : '—'}
                            </span>
                            {detail.evidence && (
                              <span className="rule-evidence-text">Match: "{detail.evidence}"</span>
                            )}
                          </td>
                          <td className="field-confidence-cell">
                            <div className="confidence-cell-group">
                              <span className={`confidence-badge-pill ${confObj.cls}`}>
                                {confObj.pct !== undefined ? `${confObj.pct}%` : 'N/A'}
                              </span>
                              <span className="confidence-level-tag">{confObj.label}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* C. LLM EXTRACTION TAB */}
        {activeTab === 'llm' && (
          <div className="tab-panel">
            {Object.keys(llm_extraction || {}).length === 0 ? (
              <div className="empty-sub-state">
                <Cpu size={28} />
                <p>No LLM extraction candidates found.</p>
                <span className="empty-sub">
                  Verify that LLM Extraction is enabled under AI Configuration.
                </span>
              </div>
            ) : (
              <div className="table-responsive-container">
                <table className="enterprise-data-table extraction-table">
                  <thead>
                    <tr>
                      <th style={{ width: '30%' }}>Field</th>
                      <th style={{ width: '45%' }}>LLM Extracted Value</th>
                      <th style={{ width: '25%' }}>LLM Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(llm_extraction).map(([key, detail]) => {
                      const confObj = getConfidenceTier(detail.confidence);
                      return (
                        <tr key={key}>
                          <td className="field-name-cell">
                            <strong>{formatFieldLabel(key)}</strong>
                            <span className="field-key-slug">{key}</span>
                          </td>
                          <td className="field-value-cell">
                            <span className={detail.value ? 'value-present' : 'value-missing'}>
                              {detail.value !== null && detail.value !== undefined
                                ? String(detail.value)
                                : '—'}
                            </span>
                            {detail.evidence && (
                              <span className="llm-evidence-text">Context: "{detail.evidence}"</span>
                            )}
                          </td>
                          <td className="field-confidence-cell">
                            <div className="confidence-cell-group">
                              <span className={`confidence-badge-pill ${confObj.cls}`}>
                                {confObj.pct !== undefined ? `${confObj.pct}%` : 'N/A'}
                              </span>
                              <span className="confidence-level-tag">{confObj.label}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* D. COMPARISON TAB */}
        {activeTab === 'comparison' && (
          <div className="tab-panel">
            <div className="table-responsive-container">
              <table className="enterprise-data-table extraction-table">
                <thead>
                  <tr>
                    <th style={{ width: '20%' }}>Field</th>
                    <th style={{ width: '22%' }}>Rule Value</th>
                    <th style={{ width: '22%' }}>LLM Value</th>
                    <th style={{ width: '20%' }}>Final Reconciled</th>
                    <th style={{ width: '16%' }}>Reconciliation Status</th>
                  </tr>
                </thead>
                <tbody>
                  {allFieldKeys.map((key) => {
                    const ruleVal = rule_extraction[key]?.value;
                    const llmVal = llm_extraction[key]?.value;
                    const reconDetail = reconciliation[key] || {};
                    const finalVal = final_result[key] ?? reconDetail.value;
                    const compStatus = reconDetail.status || (ruleVal === llmVal ? 'AGREED' : 'REVIEW REQUIRED');

                    return (
                      <tr key={key}>
                        <td className="field-name-cell">
                          <strong>{formatFieldLabel(key)}</strong>
                        </td>
                        <td className="comparison-val-cell rule-val">
                          <span>{ruleVal !== null && ruleVal !== undefined ? String(ruleVal) : '—'}</span>
                        </td>
                        <td className="comparison-val-cell llm-val">
                          <span>{llmVal !== null && llmVal !== undefined ? String(llmVal) : '—'}</span>
                        </td>
                        <td className="comparison-val-cell final-val">
                          <strong>
                            {finalVal !== null && finalVal !== undefined ? String(finalVal) : '—'}
                          </strong>
                        </td>
                        <td className="field-status-cell">
                          {renderComparisonStatusBadge(compStatus)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
