import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import UniversalDocumentViewer from '../dynamic/UniversalDocumentViewer';

export default function DocumentDetailsView({ docId: propDocId, onBack }) {
  const params = useParams();
  const navigate = useNavigate();
  const docId = propDocId || params.id;

  const handleClose = () => {
    if (onBack) {
      onBack();
    } else {
      navigate('/documents');
    }
  };

  if (!docId) return null;

  return (
    <UniversalDocumentViewer
      docId={docId}
      isOpen={true}
      onClose={handleClose}
      onDocumentUpdated={handleClose}
    />
  );
}
