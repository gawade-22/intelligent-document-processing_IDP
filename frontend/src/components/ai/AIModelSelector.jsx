import React from 'react';
import { Box, Layers } from 'lucide-react';

export default function AIModelSelector({ provider, value, onChange, supportedModels = {} }) {
  const modelsForProvider = supportedModels[provider] || [
    'gemini-1.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-pro',
  ];

  return (
    <div className="form-group ai-field-group">
      <label htmlFor="ai-model-input" className="form-label">
        <Box size={15} className="inline-icon text-primary" />
        Configured Model
      </label>
      <div className="model-input-wrapper">
        <input
          id="ai-model-input"
          type="text"
          className="form-input code-font"
          value={value || ''}
          placeholder="e.g. gemini-1.5-flash"
          onChange={(e) => onChange(e.target.value)}
        />
      </div>

      <div className="model-quick-chips">
        <span className="chips-label">Quick select:</span>
        {modelsForProvider.map((m) => (
          <button
            key={m}
            type="button"
            className={`chip-btn ${value === m ? 'chip-active' : ''}`}
            onClick={() => onChange(m)}
          >
            {m}
          </button>
        ))}
      </div>
      <span className="form-hint">
        Backend remains the source of truth for model execution. Any valid model identifier supported by the provider may be entered.
      </span>
    </div>
  );
}
