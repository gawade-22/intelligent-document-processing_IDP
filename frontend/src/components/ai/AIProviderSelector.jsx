import React from 'react';
import { Server, Sparkles } from 'lucide-react';

export default function AIProviderSelector({ value, onChange, supportedProviders = [] }) {
  const providerOptions = [
    { id: 'gemini', name: 'Google Gemini (Recommended)', desc: 'Official Google Gemini 1.5/2.0 API with high precision' },
    { id: 'openai_compatible', name: 'OpenAI-Compatible REST API', desc: 'Any OpenAI, Groq, OpenRouter, or self-hosted endpoint' },
    { id: 'mock', name: 'Mock Provider (Offline Testing)', desc: 'Deterministic test responses with zero network calls' },
    { id: 'noop', name: 'Disabled (NoOp)', desc: 'Bypass AI extraction and use rule-based pipeline exclusively' },
  ];

  return (
    <div className="form-group ai-field-group">
      <label htmlFor="ai-provider-select" className="form-label">
        <Server size={15} className="inline-icon text-primary" />
        LLM Provider
      </label>
      <select
        id="ai-provider-select"
        className="form-select"
        value={value || 'gemini'}
        onChange={(e) => onChange(e.target.value)}
      >
        {providerOptions.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
      <span className="form-hint">
        {providerOptions.find((p) => p.id === value)?.desc ||
          'Select the backend LLM engine responsible for parsing untrusted document text.'}
      </span>
    </div>
  );
}
