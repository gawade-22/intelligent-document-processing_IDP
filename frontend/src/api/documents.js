/**
 * IDP Documents API Service
 * Handles:
 * - GET    /api/documents
 * - GET    /api/documents/{id}
 * - GET    /api/documents/review
 * - POST   /api/documents/{id}/verify
 * - POST   /api/documents/upload
 * - POST   /api/documents/{id}/process
 * - File streaming URL: /api/documents/{id}/file
 */

import { apiClient, BASE_URL } from './client';

/**
 * Fetch paginated & filtered documents list
 */
export async function getDocuments({
  page = 1,
  pageSize = 10,
  page_size = 10,
  status = null,
  documentType = null,
  document_type = null,
  vendorName = null,
  vendor_name = null,
  invoiceNumber = null,
  invoice_number = null,
} = {}) {
  const query = new URLSearchParams();
  const effectivePage = page || 1;
  const effectivePageSize = pageSize || page_size || 10;

  query.append('page', String(effectivePage));
  query.append('page_size', String(effectivePageSize));

  const effectiveStatus = status;
  if (effectiveStatus && effectiveStatus !== 'ALL') {
    query.append('status', effectiveStatus);
  }

  const effectiveType = documentType || document_type;
  if (effectiveType && effectiveType !== 'ALL') {
    query.append('document_type', effectiveType);
  }

  const effectiveVendor = vendorName || vendor_name;
  if (effectiveVendor && effectiveVendor.trim()) {
    query.append('vendor_name', effectiveVendor.trim());
  }

  const effectiveInvoice = invoiceNumber || invoice_number;
  if (effectiveInvoice && effectiveInvoice.trim()) {
    query.append('invoice_number', effectiveInvoice.trim());
  }

  return await apiClient(`/api/documents?${query.toString()}`);
}

/**
 * Fetch single document details by ID (GET /api/documents/{id})
 */
export async function getDocumentById(id) {
  return await apiClient(`/api/documents/${id}`);
}

/**
 * Fetch Universal HITL Review Queue documents (GET /api/documents/review)
 */
export async function getReviewDocuments() {
  return await apiClient('/api/documents/review');
}

/**
 * Submit HITL manual verification/corrections (POST /api/documents/{id}/verify)
 */
export async function verifyDocument(id, fields, reviewerId = 'reviewer', notes = null) {
  return await apiClient(`/api/documents/${id}/verify`, {
    method: 'POST',
    body: JSON.stringify({
      fields,
      reviewer_id: reviewerId,
      notes,
    }),
  });
}

/**
 * Upload a document (PDF, Excel, CSV, Image) (POST /api/documents/upload)
 */
export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  return await apiClient('/api/documents/upload', {
    method: 'POST',
    body: formData,
  });
}

/**
 * Trigger backend pipeline processing on an uploaded document (POST /api/documents/{id}/process)
 */
export async function processDocument(id) {
  return await apiClient(`/api/documents/${id}/process`, {
    method: 'POST',
  });
}

/**
 * Get direct file stream URL for viewing in browser or iframe
 */
export function getDocumentFileUrl(id) {
  return `${BASE_URL}/api/documents/${id}/file`;
}
