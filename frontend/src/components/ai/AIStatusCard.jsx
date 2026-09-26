import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Zap,
  RefreshCw,
} from 'lucide-react';
import { testAIConnection } from '../../api/ai';

export default function AIStatusCard({ config, onRefresh, isLoading }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const provider = config?.provider || 'gemini';
  const model = config?.model || 'gemini-1.5-flash';
  const enabled = config?.enabled !== false;
  const hasApiKey = Boolean(config?.has_api_key || config?.api_key_configured);
  const status = config?.status;

  // Determine badge state
  let statusInfo = {
    label: 'Not Configured',
    cls: 'status-pill-amber',
    dotCls: 'dot-amber',
  };

  if (!enabled) {
    statusInfo = {
      label: 'Disabled',
      cls: 'status-pill-gray',
      dotCls: 'dot-gray',
    };
  } else if (hasApiKey && (status === 'READY' || status === 'CONNECTED')) {
    statusInfo = {
      label: 'Connected',
      cls: 'status-pill-green',
      dotCls: 'dot-green',
    };
  } else if (status === 'CONNECTION_FAILED' || status === 'ERROR') {
    statusInfo = {
      label: 'Connection Failed',
      cls: 'status-pill-red',
      dotCls: 'dot-red',
    };
  } else if (!hasApiKey) {
    statusInfo = {
      label: 'Not Configured',
      cls: 'status-pill-amber',
      dotCls: 'dot-amber',
    };
  }

  // Handle Connection Test
  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      const resp = await testAIConnection({
        provider,
        model,
      });
      setTestResult({
        success: resp.success,
        message: resp.success
          ? 'Connected successfully'
          : resp.message || 'Connection failed',
        providerName: resp.provider === 'gemini' ? 'Google Gemini' : resp.provider,
        modelName: resp.model,
        latency: resp.details?.latency_ms,
      });
      if (resp.success && onRefresh) {
        onRefresh();
      }
    } catch (err) {
      setTestResult({
        success: false,
        message: 'Unable to reach backend service.',
      });
    } finally {
      setTesting(false);
    }
  };

  const providerDisplay =
    provider === 'gemini'
      ? 'Google Gemini'
      : provider === 'openai_compatible'
      ? 'OpenAI-Compatible'
      : provider === 'mock'
      ? 'Mock Provider'
      : provider;

  return (
    <div className="ai-card status-card-clean">
      <div className="card-header-clean">
        <div className="card-title-row">
          <h3 className="card-title-clean">AI Status</h3>
          <span className={`clean-status-pill ${statusInfo.cls}`}>
            <span className={`clean-dot ${statusInfo.dotCls}`} />
            {statusInfo.label}
          </span>
        </div>
      </div>

      {/* Compact Info List */}
      <div className="status-metric-rows">
        <div className="status-row">
          <span className="status-row-label">Provider</span>
          <span className="status-row-value">{providerDisplay}</span>
        </div>

        <div className="status-row">
          <span className="status-row-label">Model</span>
          <span className="status-row-value font-mono">{model}</span>
        </div>

        <div className="status-row">
          <span className="status-row-label">Extraction Mode</span>
          <span className="status-row-value">
            {enabled ? (
              <span className="mode-badge-rule-ai">Rule + AI</span>
            ) : (
              <span className="mode-badge-rule-only">Rule Only</span>
            )}
          </span>
        </div>

        <div className="status-row">
          <span className="status-row-label">API Key</span>
          <span className="status-row-value">
            {hasApiKey ? (
              <span className="key-badge-configured">Configured ✓</span>
            ) : (
              <span className="key-badge-missing">Not configured</span>
            )}
          </span>
        </div>
      </div>

      {/* Test Connection Action */}
      <div className="status-card-actions">
        <button
          type="button"
          className="btn btn-secondary btn-sm test-btn-full"
          onClick={handleTestConnection}
          disabled={testing || isLoading || !hasApiKey}
          title={!hasApiKey ? 'Configure an API key to test connection' : 'Test AI Connection'}
        >
          {testing ? (
            <RefreshCw size={14} className="spinning" />
          ) : (
            <Zap size={14} className="text-primary" />
          )}
          <span>{testing ? 'Testing connection...' : 'Test Connection'}</span>
        </button>

        {!hasApiKey && (
          <span className="status-sub-hint">Add API key to test connection</span>
        )}
      </div>

      {/* Connection Result Banner */}
      {testResult && (
        <div
          className={`test-feedback-banner ${
            testResult.success ? 'feedback-success' : 'feedback-error'
          }`}
          role="status"
        >
          {testResult.success ? (
            <CheckCircle2 size={16} className="text-green flex-shrink-0" />
          ) : (
            <XCircle size={16} className="text-red flex-shrink-0" />
          )}
          <div className="feedback-text">
            <span className="feedback-title">
              {testResult.success ? '✓ Connected successfully' : '✕ Connection failed'}
            </span>
            {testResult.success && (
              <span className="feedback-details">
                {testResult.providerName} · {testResult.modelName}
                {testResult.latency ? ` · ${testResult.latency}ms` : ''}
              </span>
            )}
            {!testResult.success && (
              <span className="feedback-details">{testResult.message}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
