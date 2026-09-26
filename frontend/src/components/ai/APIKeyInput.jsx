import React, { useState } from 'react';
import { Key, Eye, EyeOff, ShieldCheck, Lock, Trash2, CheckCircle2 } from 'lucide-react';

export default function APIKeyInput({
  provider = 'gemini',
  isConfigured = false,
  maskedKey = null,
  onSaveKey,
  onClearKey,
  isSaving = false,
}) {
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [successMsg, setSuccessMsg] = useState(null);

  const providerLabel = provider === 'gemini' ? 'Google Gemini' : 'OpenAI-Compatible';

  const handleSave = async (e) => {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;
    if (onSaveKey) {
      await onSaveKey(apiKeyInput.trim());
      setApiKeyInput('');
      setSuccessMsg('API key saved and securely encrypted on backend.');
      setTimeout(() => setSuccessMsg(null), 4000);
    }
  };

  const handleClear = async () => {
    if (onClearKey) {
      await onClearKey();
      setApiKeyInput('');
      setSuccessMsg('API key cleared from backend configuration.');
      setTimeout(() => setSuccessMsg(null), 4000);
    }
  };

  return (
    <div className="form-group ai-field-group api-key-card">
      <div className="api-key-header">
        <label htmlFor="ai-api-key" className="form-label mb-0">
          <Key size={15} className="inline-icon text-primary" />
          {providerLabel} API Key
        </label>
        {isConfigured && (
          <span className="badge-secure-status">
            <Lock size={12} className="inline-icon" />
            Configured on Backend
          </span>
        )}
      </div>

      <div className="api-key-controls">
        <div className="password-input-container">
          <input
            id="ai-api-key"
            type={showPassword ? 'text' : 'password'}
            className="form-input code-font"
            placeholder={
              isConfigured
                ? '•••••••••••••••••••••••••••• (Key is active; enter new key to overwrite)'
                : 'Enter your API key (e.g. AIzaSy...)'
            }
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            autoComplete="off"
            spellCheck="false"
          />
          {apiKeyInput && (
            <button
              type="button"
              className="toggle-password-btn"
              onClick={() => setShowPassword(!showPassword)}
              title={showPassword ? 'Hide Key' : 'Show Key'}
              aria-label={showPassword ? 'Hide Key' : 'Show Key'}
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          )}
        </div>

        <div className="api-key-btn-group">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleSave}
            disabled={!apiKeyInput.trim() || isSaving}
          >
            {isSaving ? 'Saving...' : 'Save API Key'}
          </button>

          {isConfigured && (
            <button
              type="button"
              className="btn btn-secondary btn-sm text-error"
              onClick={handleClear}
              disabled={isSaving}
              title="Remove stored API key from backend"
            >
              <Trash2 size={14} className="inline-icon" />
              Clear Key
            </button>
          )}
        </div>
      </div>

      {successMsg && (
        <div className="api-key-success-alert">
          <CheckCircle2 size={14} className="text-success inline-icon" />
          {successMsg}
        </div>
      )}

      <div className="security-notice-callout">
        <ShieldCheck size={14} className="text-primary inline-icon flex-shrink-0 mt-1" />
        <span>
          <strong>Enterprise Security Guarantee:</strong> The API key is stored strictly on the server and is never sent to the React frontend or saved in browser localStorage.
        </span>
      </div>
    </div>
  );
}
