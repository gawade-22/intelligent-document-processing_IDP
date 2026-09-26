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

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(errorData.detail || `Upload error: ${response.status}`);
  }
  return response.json();
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
