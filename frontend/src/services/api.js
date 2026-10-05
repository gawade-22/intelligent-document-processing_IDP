/**
 * Intelligent Document Processing (IDP) - Frontend API Service
 * Communicates with FastAPI backend endpoints:
 * - GET    /api/documents
 * - GET    /api/documents/stats
 * - GET    /api/documents/{id}
 * - GET    /api/documents/{id}/file
 * - POST   /api/documents/upload
 * - POST   /api/documents/{id}/process
 * - POST   /api/documents/{id}/verify
 */

const API_BASE_URL = ''; // Relative path, handled by Vite proxy to localhost:8000

export async function fetchDocuments({
  page = 1,
  pageSize = 10,
  status = null,
  documentType = null,
  vendorName = null,
  invoiceNumber = null,
} = {}) {
  const query = new URLSearchParams();
  query.append('page', String(page));
  query.append('page_size', String(pageSize));

  if (status && status !== 'ALL') {
    query.append('status', status);
  }
  if (documentType && documentType !== 'ALL') {
    query.append('document_type', documentType);
  }
  if (vendorName && vendorName.trim()) {
    query.append('vendor_name', vendorName.trim());
  }
  if (invoiceNumber && invoiceNumber.trim()) {
    query.append('invoice_number', invoiceNumber.trim());
  }

  const response = await fetch(`${API_BASE_URL}/api/documents?${query.toString()}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch documents' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchStats() {
  const response = await fetch(`${API_BASE_URL}/api/documents/stats`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch stats' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentDetails(id) {
  const response = await fetch(`${API_BASE_URL}/api/documents/${id}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Document not found' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchReviewDocuments() {
  const response = await fetch(`${API_BASE_URL}/api/documents/review`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch review queue' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function uploadDocument(file, runAsync = true) {
  // Route upload requests directly to the Universal Dynamic Pipeline (v2)
  const result = await uploadDocumentV2(file, runAsync);
  return {
    id: result.document_id,
    ...result,
  };
}

export async function processDocument(id) {
  const response = await fetch(`${API_BASE_URL}/api/documents/${id}/process`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Processing failed' }));
    throw new Error(errorData.detail || `Processing error: ${response.status}`);
  }
  return response.json();
}

export async function verifyDocument(id, fields) {
  const response = await fetch(`${API_BASE_URL}/api/documents/${id}/verify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ fields }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Verification failed' }));
    throw new Error(errorData.detail || `Verification error: ${response.status}`);
  }
  return response.json();
}

export function getDocumentFileUrl(id) {
  return `${API_BASE_URL}/api/documents/${id}/file`;
}

// ----------------------------------------------------------------------------
// Universal IDP v2 Endpoints
// ----------------------------------------------------------------------------

export async function fetchDocumentV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Document not found' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentStatusV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}/status`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch status' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentStructureV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}/structure`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch structure' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentExtractionV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}/extraction`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch extraction' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentEvidenceV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}/evidence`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch evidence' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentInsightsV2(id) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${id}/insights`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch insights' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function updateFieldV2(documentId, fieldId, value, reviewerId = 'human') {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/fields/${fieldId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value, reviewer_id: reviewerId }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to update field' }));
    throw new Error(errorData.detail || `Update error: ${response.status}`);
  }
  return response.json();
}

export async function createFieldV2(documentId, fieldData) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fieldData),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to create field' }));
    throw new Error(errorData.detail || `Create error: ${response.status}`);
  }
  return response.json();
}

export async function verifyDocumentV2(documentId) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Verification failed' }));
    throw new Error(errorData.detail || `Verification error: ${response.status}`);
  }
  return response.json();
}

export async function reprocessDocumentV2(documentId) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/reprocess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Reprocessing failed' }));
    throw new Error(errorData.detail || `Reprocess error: ${response.status}`);
  }
  return response.json();
}

export async function fetchSchemasV2() {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/schemas/list`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to list schemas' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function fetchSchemaDetailV2(schemaId) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/schemas/${schemaId}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Schema not found' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function updateSchemaV2(schemaId, payload) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/schemas/${schemaId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to update schema' }));
    throw new Error(errorData.detail || `Update error: ${response.status}`);
  }
  return response.json();
}

export async function createSchemaV2(payload) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/schemas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to create schema' }));
    throw new Error(errorData.detail || `Create error: ${response.status}`);
  }
  return response.json();
}

export async function uploadDocumentV2(file, runAsync = true) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/v2/documents/upload?run_async=${runAsync}`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(errorData.detail || `Upload error: ${response.status}`);
  }
  return response.json();
}

export async function fetchDocumentRunsV2(documentId) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/runs`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch runs' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}

export async function compareDocumentRunsV2(documentId, runA, runB) {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/compare-runs?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to compare runs' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  return response.json();
}export async function downloadDocumentPdfReportV2(documentId, fileName = 'extraction_report.pdf') {
  const response = await fetch(`${API_BASE_URL}/api/v2/documents/${documentId}/pdf-report`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to download PDF report' }));
    throw new Error(errorData.detail || `Server error: ${response.status}`);
  }
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  const cleanName = fileName.replace(/\.[^/.]+$/, '');
  link.download = `${cleanName}_report.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(downloadUrl);
}
