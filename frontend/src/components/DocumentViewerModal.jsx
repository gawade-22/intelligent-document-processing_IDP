import React from 'react';
import UniversalDocumentViewer from './dynamic/UniversalDocumentViewer';

/**
 * Universal Document Viewer Modal (v2)
 * Renders dynamic schema-driven sections, fields, tables, evidence bounding box
 * overlays, deterministic validation rules, insights, and schema editing.
 * Replaces legacy 13-type hardcoded renderer.
 */
export default function DocumentViewerModal({
  docId,
  isOpen = false,
  onClose,
  onUpdateSuccess,
}) {
  if (!isOpen || !docId) return null;

  return (
    <UniversalDocumentViewer
      docId={docId}
      isOpen={isOpen}
      onClose={onClose}
      onDocumentUpdated={onUpdateSuccess}
    />
  );
}
