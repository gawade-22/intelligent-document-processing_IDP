import React, { useState, useEffect } from 'react';
import {
  Save,
  Key,
  Eye,
  EyeOff,
  Trash2,
  CheckCircle2,
} from 'lucide-react';

export const PROVIDER_OPTIONS = [
  { id: 'gemini', label: 'Google Gemini' },
  { id: 'openai_compatible', label: 'OpenAI-Compatible' },
  { id: 'mock', label: 'Mock Provider (Testing)' },
];

export const DEFAULT_MODELS = {
  gemini: ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro'],
  openai_compatible: ['gpt-4o-mini', 'gpt-4o', 'claude-3-5-sonnet'],
  mock: ['mock-model-v1'],
};

export default function AIConfigCard({
  config,
  onSaveConfig,
  onClearKey,
  isSaving = false,
}) {
  const [provider, setProvider] = useState('gemini');
  const [model, setModel] = useState('gemini-1.5-flash');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [successMsg, setSuccessMsg] = useState(null);

  const hasApiKey = Boolean(config?.has_api_key || config?.api_key_configured);

  useEffect(() => {
    if (config) {
      if (config.provider) setProvider(config.provider);
      if (config.model) setModel(config.model);
    }
  }, [config]);

  const handleProviderSelect = (e) => {
    const newProv = e.target.value;
    setProvider(newProv);
    const defaults = DEFAULT_MODELS[newProv] || [];
    if (defaults.length > 0) {
      setModel(defaults[0]);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (onSaveConfig) {
      const payload = {
        provider,
        model,
      };
      if (apiKeyInput.trim()) {
        payload.api_key = apiKeyInput.trim();
      }
      await onSaveConfig(payload);
      setApiKeyInput('');
      setSuccessMsg('Configuration saved.');
      setTimeout(() => setSuccessMsg(null), 3000);
    }
  };

  const handleClear = async () => {
    if (onClearKey) {
      await onClearKey();
      setApiKeyInput('');
      setSuccessMsg('API key cleared.');
      setTimeout(() => setSuccessMsg(null), 3000);
    }
  };

  const availableModels = DEFAULT_MODELS[provider] || [];
  const providerLabel = provider === 'gemini' ? 'Gemini' : 'Provider';

  return (
    <div className="ai-card config-card-clean">
      <div className="card-header-clean">
        <h3 className="card-title-clean">AI Configuration</h3>
        <p className="card-subtitle-clean">
          Select your AI provider, model, and credentials.
        </p>
      </div>

      {successMsg && (
        <div className="alert-inline alert-inline-success">
          <CheckCircle2 size={15} />
          <span>{successMsg}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="clean-config-form">
        {/* Provider Field */}
        <div className="clean-form-group">
          <label htmlFor="ai-provider-select" className="clean-label">
            AI Provider
          </label>
          <select
            id="ai-provider-select"
            className="clean-select"
            value={provider}
            onChange={handleProviderSelect}
            disabled={isSaving}
          >
            {PROVIDER_OPTIONS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        {/* Model Field */}
        <div className="clean-form-group">
          <label htmlFor="ai-model-input" className="clean-label">
            Model
          </label>
          <div className="model-input-group">
            <input
              id="ai-model-input"
              type="text"
              className="clean-input font-mono"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gemini-1.5-flash"
              disabled={isSaving}
            />
          </div>

          {availableModels.length > 0 && (
            <div className="model-chips-row">
              {availableModels.map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`model-chip ${model === m ? 'chip-active' : ''}`}
                  onClick={() => setModel(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* API Key Field */}
        <div className="clean-form-group">
          <div className="label-with-status">
            <label htmlFor="ai-api-key-input" className="clean-label">
              {providerLabel} API Key
            </label>
            <span className="key-status-text">
              {hasApiKey ? (
                <span className="key-status-active">● Configured ✓</span>
              ) : (
                <span className="key-status-missing">○ Not configured</span>
              )}
            </span>
          </div>

          <div className="password-input-box">
            <input
              id="ai-api-key-input"
              type={showPassword ? 'text' : 'password'}
              className="clean-input font-mono"
              placeholder={
                hasApiKey
                  ? '•••••••••••••••• (Enter new key to update)'
                  : 'Enter API key...'
              }
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              disabled={isSaving}
              autoComplete="off"
            />
            {apiKeyInput && (
              <button
                type="button"
                className="eye-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? 'Hide Key' : 'Show Key'}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            )}
          </div>

          {hasApiKey && (
            <div className="key-action-hint-row">
              <span className="key-secure-note">
                Key is stored securely on the backend.
              </span>
              <button
                type="button"
                className="btn-link-danger"
                onClick={handleClear}
                disabled={isSaving}
              >
                <Trash2 size={12} />
                <span>Clear Key</span>
              </button>
            </div>
          )}
        </div>

        {/* Single Primary Save Action */}
        <div className="config-card-footer">
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={isSaving}
          >
            <Save size={14} />
            <span>{isSaving ? 'Saving...' : 'Save Configuration'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
