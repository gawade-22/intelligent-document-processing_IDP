/**
 * IDP Dashboard API Service
 * Endpoint: GET /api/documents/stats
 */

import { apiClient } from './client';

/**
 * Fetch dashboard summary statistics (processed, verified, needing review, average confidence)
 */
export async function getDashboardStats() {
  return await apiClient('/api/documents/stats');
}
