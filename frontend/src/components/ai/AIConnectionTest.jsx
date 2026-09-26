import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  Activity,
  RefreshCw,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import { testAIConnection } from '../../api/ai';

export default function AIConnectionTest({
  provider,
  model,
  onTestComplete,
  disabled = false,
}) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);

  const handleTest = async () => {
    setTesting(true);
    setResult(null);

    try {
      const resp = await testAIConnection({
        provider: provider || undefined,
        model: model || undefined,
      });
      setResult(resp);
      if (onTestComplete) {
        onTestComplete(resp);
      }
    } catch (err) {
      setResult({
        success: false,
        status: 'CONNECTION_FAILED',
        provider: provider || 'Unknown',
        model: model || 'Unknown',
        message: err.message || 'Connection test failed to reach backend API.',
      });
      if (onTestComplete) {
        onTestComplete({ success: false });
      }
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="ai-connection-test-container">
      <div className="test-action-row">
        <button
          type="button"
          className="btn btn-secondary test-connection-btn"
          onClick={handleTest}
          disabled={testing || disabled}
        >
          {testing ? (
            <RefreshCw size={15} className="spinning" />
          ) : (
            <Zap size={15} className="text-primary" />
          )}
          <span>{testing ? 'Testing LLM Connectivity...' : 'Test LLM Connection'}</span>
        </button>

        <span className="test-hint">
          Pings backend-configured LLM endpoint to verify authentication, model availability, and response latency.
        </span>
      </div>

      {result && (
        <div
          className={`connection-result-banner ${
            result.success ? 'result-success' : 'result-failure'
          }`}
          role="status"
        >
          <div className="result-icon-wrapper">
            {result.success ? (
              <CheckCircle2 size={20} className="icon-success" />
            ) : (
              <XCircle size={20} className="icon-failure" />
            )}
          </div>

          <div className="result-info">
            <div className="result-header-line">
              <span className="result-title">
                {result.success ? '✓ Connection successful' : '✕ Connection failed'}
              </span>
              <span className="result-meta-pill">
                Provider: <strong>{result.provider}</strong>
              </span>
              <span className="result-meta-pill">
                Model: <strong>{result.model}</strong>
              </span>
              {result.details?.latency_ms && (
                <span className="result-meta-pill latency">
                  {result.details.latency_ms} ms
                </span>
              )}
            </div>

            <p className="result-message">{result.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}
