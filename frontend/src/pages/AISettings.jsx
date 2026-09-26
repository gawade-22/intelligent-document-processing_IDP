import React, { useState, useEffect, useCallback } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  Sliders,
  Save,
} from 'lucide-react';
import { getAIConfig, updateAIConfig } from '../api/ai';
import AIStatusCard from '../components/ai/AIStatusCard';
import AIConfigCard from '../components/ai/AIConfigCard';
import PromptEditor from '../components/ai/PromptEditor';

export default function AISettings() {
  const [config, setConfig] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState(null);

  // Advanced settings state
  const [timeout, setTimeoutVal] = useState(30);
  const [maxInputChars, setMaxInputChars] = useState(12000);
  const [selectedDocType, setSelectedDocType] = useState('invoice');

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getAIConfig();
      setConfig(data);
      if (data.timeout) setTimeoutVal(data.timeout);
      if (data.max_input_characters) setMaxInputChars(data.max_input_characters);
    } catch (err) {
      showToast(err.message || 'Unable to load AI configuration.', 'error');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Handle Enable/Disable Toggle
  const handleToggleEnabled = async (checked) => {
    setIsSaving(true);
    try {
      const updated = await updateAIConfig({ enabled: checked });
      setConfig(updated);
      showToast(
        checked
          ? 'AI extraction enabled (Rule + AI).'
          : 'AI extraction disabled (Rule-only).',
        'success'
      );
    } catch (err) {
      showToast(err.message || 'Failed to toggle AI extraction.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  // Save General Configuration (Provider, Model, Key)
  const handleSaveConfig = async (payload) => {
    setIsSaving(true);
    try {
      const updated = await updateAIConfig(payload);
      setConfig(updated);
      showToast('AI configuration saved.', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to save AI configuration.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  // Clear Key
  const handleClearKey = async () => {
    setIsSaving(true);
    try {
      const updated = await updateAIConfig({ clear_api_key: true });
      setConfig(updated);
      showToast('API key cleared.', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to clear API key.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  // Save Prompt
  const handleSavePrompt = async (promptText) => {
    setIsSaving(true);
    try {
      const updated = await updateAIConfig({ custom_prompt: promptText });
      setConfig(updated);
      showToast('Extraction prompt saved.', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to save prompt.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  // Save Advanced Settings
  const handleSaveAdvanced = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const updated = await updateAIConfig({
        timeout: parseInt(timeout, 10) || 30,
        max_input_characters: parseInt(maxInputChars, 10) || 12000,
      });
      setConfig(updated);
      showToast('Advanced settings saved.', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to save advanced settings.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  const isEnabled = config?.enabled !== false;

  return (
    <div className="ai-page-clean">
      {/* Toast Alert */}
      {toast && (
        <div className={`app-toast toast-${toast.type}`}>
          {toast.type === 'error' ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* 1. Prominent Enable Card */}
      <div className="ai-card ai-enable-card">
        <div className="enable-text-group">
          <div className="enable-title-row">
            <span className="enable-card-title">AI Extraction</span>
            <span className={`enable-pill ${isEnabled ? 'pill-on' : 'pill-off'}`}>
              {isEnabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <p className="enable-card-desc">
            {isEnabled
              ? 'AI-powered extraction is enabled (Rule Extraction + Gemini AI).'
              : 'AI extraction is disabled (Rule Extraction only).'}
          </p>
        </div>

        <label className="switch-toggle" htmlFor="ai-toggle-switch">
          <input
            id="ai-toggle-switch"
            type="checkbox"
            checked={isEnabled}
            onChange={(e) => handleToggleEnabled(e.target.checked)}
            disabled={isSaving || isLoading}
          />
          <span className="slider-round" />
        </label>
      </div>

      {/* 2. Clean Two-Column Layout: Left = Config, Right = Status */}
      <div className="ai-two-col-grid">
        <AIConfigCard
          config={config}
          onSaveConfig={handleSaveConfig}
          onClearKey={handleClearKey}
          isSaving={isSaving}
        />

        <AIStatusCard
          config={config}
          onRefresh={loadConfig}
          isLoading={isLoading}
        />
      </div>

      {/* 3. Extraction Prompt Card */}
      <PromptEditor
        currentPrompt={config?.custom_prompt}
        onSavePrompt={handleSavePrompt}
        selectedDocType={selectedDocType}
        onDocTypeChange={(t) => setSelectedDocType(t)}
        isSaving={isSaving}
      />

      {/* 4. Collapsible Advanced Settings */}
      <details className="ai-card advanced-accordion">
        <summary className="advanced-summary">
          <span className="summary-title">Advanced Settings</span>
          <span className="summary-indicator">▾</span>
        </summary>

        <form onSubmit={handleSaveAdvanced} className="advanced-form-content">
          <p className="advanced-subtext">
            Optional parameters for request timeouts and input limits.
          </p>

          <div className="advanced-fields-row">
            <div className="clean-form-group">
              <label htmlFor="ai-timeout" className="clean-label">
                Timeout (seconds)
              </label>
              <input
                id="ai-timeout"
                type="number"
                min="5"
                max="120"
                className="clean-input"
                value={timeout}
                onChange={(e) => setTimeoutVal(e.target.value)}
              />
            </div>

            <div className="clean-form-group">
              <label htmlFor="ai-max-chars" className="clean-label">
                Max Document Characters
              </label>
              <input
                id="ai-max-chars"
                type="number"
                min="1000"
                max="50000"
                step="500"
                className="clean-input"
                value={maxInputChars}
                onChange={(e) => setMaxInputChars(e.target.value)}
              />
            </div>
          </div>

          <div className="advanced-actions-row">
            <button
              type="submit"
              className="btn btn-secondary btn-sm"
              disabled={isSaving}
            >
              <Save size={13} />
              <span>Save Advanced Settings</span>
            </button>
          </div>
        </form>
      </details>
    </div>
  );
}
