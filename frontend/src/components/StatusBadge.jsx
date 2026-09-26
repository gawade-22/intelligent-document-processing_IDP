import React from 'react';
import {
  FileText,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Loader2,
} from 'lucide-react';

/**
 * Reusable StatusBadge Component
 * Supported backend statuses:
 * - UPLOADED     -> "UPLOADED" (Slate/Neutral)
 * - PROCESSING   -> "Processing" (Blue with spinner)
 * - VERIFIED     -> "Verified" (Green with check)
 * - NEEDS_REVIEW -> "Needs Review" (Amber with warning)
 * - FAILED       -> "Failed" (Red with alert)
 *
 * Designed to not rely solely on color (includes status-specific icons, labels, and borders).
 */
export default function StatusBadge({ status = 'UPLOADED', className = '' }) {
  const normStatus = (status || '').toUpperCase().trim();

  let label = 'UPLOADED';
  let badgeClass = 'status-uploaded';
  let Icon = FileText;
  let isSpinning = false;

  switch (normStatus) {
    case 'VERIFIED':
      label = 'Verified';
      badgeClass = 'status-verified';
      Icon = CheckCircle2;
      break;

    case 'NEEDS_REVIEW':
      label = 'Needs Review';
      badgeClass = 'status-needs-review';
      Icon = AlertTriangle;
      break;

    case 'FAILED':
      label = 'Failed';
      badgeClass = 'status-failed';
      Icon = AlertCircle;
      break;

    case 'PROCESSING':
      label = 'Processing';
      badgeClass = 'status-processing';
      Icon = Loader2;
      isSpinning = true;
      break;

    case 'UPLOADED':
    default:
      label = 'UPLOADED';
      badgeClass = 'status-uploaded';
      Icon = FileText;
      break;
  }

  return (
    <span
      className={`status-badge ${badgeClass} ${className}`}
      title={`Document status: ${label}`}
    >
      <Icon
        size={12}
        className={`status-badge-icon ${isSpinning ? 'spinning' : ''}`}
        aria-hidden="true"
      />
      <span className="status-badge-text">{label}</span>
    </span>
  );
}
