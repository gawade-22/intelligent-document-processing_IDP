/**
 * IDP AI / LLM Configuration and Extraction API Service
 * Securely communicates with FastAPI backend for:
 * - GET    /api/ai/config
 * - PUT    /api/ai/config
 * - POST   /api/ai/test-connection
 * - POST   /api/ai/prompt/preview
 * - GET    /api/documents/{id}/extraction
 * - POST   /api/documents/{id}/ai-extract
 */

import { apiClient } from './client';

/**
 * Fetch active AI configuration state (masked API key, enabled status, provider, model)
 */
export async function getAIConfig() {
  return await apiClient('/api/ai/config');
}

/**
 * Update runtime AI configuration (provider, model, enabled toggle, API key)
 */
export async function updateAIConfig(payload) {
  return await apiClient('/api/ai/config', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

/**
 * Test connectivity with the active or requested AI provider
 */
export async function testAIConnection(payload = {}) {
  return await apiClient('/api/ai/test-connection', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Request transparent 5-tier prompt preview for a document type
 */
export async function previewPrompt(payload = {}) {
  return await apiClient('/api/ai/prompt/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get multi-tier extraction breakdown for a document
 * Returns Rule Extraction, LLM Extraction, Reconciliation, and Final Result comparison
 */
export async function getDocumentExtraction(documentId) {
  return await apiClient(`/api/documents/${documentId}/extraction`);
}

/**
 * Execute AI extraction on a document with specified method ('rule_plus_llm', 'llm', 'rule')
 */
export async function runAIExtraction(documentId, method = 'rule_plus_llm', documentType = null) {
  const params = new URLSearchParams();
  if (method) params.append('method', method);
  if (documentType) params.append('document_type', documentType);

  const query = params.toString() ? `?${params.toString()}` : '';
  return await apiClient(`/api/documents/${documentId}/ai-extract${query}`, {
    method: 'POST',
  });
}
