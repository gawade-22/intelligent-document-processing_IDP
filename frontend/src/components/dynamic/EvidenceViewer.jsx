import React, { useState, useEffect, useRef } from 'react';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  MapPin,
  FileText,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { getDocumentFileUrl } from '../../services/api';

export default function EvidenceViewer({
  documentId,
  fileType = 'pdf',
  activeField = null,
  structure = null,
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [canvasDimensions, setCanvasDimensions] = useState({ width: 612, height: 792 });
  const containerRef = useRef(null);

  // Derive total pages from structure or default to 1
  const totalPages = structure?.document?.page_count || structure?.pages?.length || 1;

  // Auto-switch page when activeField specifies a different page
  useEffect(() => {
    if (activeField?.evidence?.page) {
      setCurrentPage(activeField.evidence.page);
    }
  }, [activeField]);

  // Read page dimensions from UniversalDocument structure for the current page
  useEffect(() => {
    if (structure?.pages) {
      const pageInfo = structure.pages.find((p) => p.n === currentPage);
      if (pageInfo && pageInfo.width && pageInfo.height) {
        setCanvasDimensions({ width: pageInfo.width, height: pageInfo.height });
      }
    }
  }, [structure, currentPage]);

  const handleZoomIn = () => setZoomLevel((z) => Math.min(2.5, z + 0.2));
  const handleZoomOut = () => setZoomLevel((z) => Math.max(0.6, z - 0.2));
  const handleResetZoom = () => setZoomLevel(1.0);

  const fileUrl = documentId ? getDocumentFileUrl(documentId) : '';
  const isPdf = fileType?.toLowerCase() === 'pdf';

  // Compute normalized bounding box coordinates for highlight overlay
  const activeBbox = activeField?.evidence?.bbox;
  const isGrounded = activeField?.evidence?.grounded;
  const bboxPage = activeField?.evidence?.page || 1;

  const hasValidBbox =
    activeBbox &&
    Array.isArray(activeBbox) &&
    activeBbox.length === 4 &&
    activeBbox.some((coord) => coord > 0) &&
    bboxPage === currentPage;

  // Bbox is [x0, y0, x1, y1] in PDF point coordinates
  const bboxStyle = hasValidBbox
    ? {
        left: `${(activeBbox[0] / canvasDimensions.width) * 100}%`,
        top: `${(activeBbox[1] / canvasDimensions.height) * 100}%`,
        width: `${((activeBbox[2] - activeBbox[0]) / canvasDimensions.width) * 100}%`,
        height: `${((activeBbox[3] - activeBbox[1]) / canvasDimensions.height) * 100}%`,
      }
    : null;

  return (
    <div className="uv-left-pane">
      {/* Top Evidence & Zoom Toolbar */}
      <div className="uv-evidence-bar">
        <div className="flex items-center gap-3">
          <span className="font-bold flex items-center gap-1.5 text-slate-200">
            <FileText size={14} className="text-blue-400" />
            Source Document
          </span>
          <span className="text-slate-400 text-xs font-mono uppercase bg-slate-800 px-2 py-0.5 rounded">
            {fileType || 'PDF'}
          </span>
        </div>

        {/* Page Navigation & Zoom Controls */}
        <div className="uv-evidence-controls">
          <div className="flex items-center gap-1 bg-slate-800/80 rounded-md p-0.5 border border-slate-700">
            <button
              type="button"
              className="p-1 text-slate-300 hover:text-white disabled:opacity-30"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              title="Previous Page"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="text-xs font-mono text-slate-300 px-1.5">
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              className="p-1 text-slate-300 hover:text-white disabled:opacity-30"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
              title="Next Page"
            >
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="flex items-center gap-1 bg-slate-800/80 rounded-md p-0.5 border border-slate-700">
            <button
              type="button"
              className="p-1 text-slate-300 hover:text-white"
              onClick={handleZoomOut}
              title="Zoom Out"
            >
              <ZoomOut size={14} />
            </button>
            <span className="text-xs font-mono text-slate-300 px-1 cursor-pointer" onClick={handleResetZoom}>
              {Math.round(zoomLevel * 100)}%
            </span>
            <button
              type="button"
              className="p-1 text-slate-300 hover:text-white"
              onClick={handleZoomIn}
              title="Zoom In"
            >
              <ZoomIn size={14} />
            </button>
          </div>

          {fileUrl && (
            <a
              href={fileUrl}
              target="_blank"
              rel="noreferrer"
              className="uv-icon-btn"
              title="Open full file in new tab"
            >
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </div>

      {/* Document View Canvas / IFrame */}
      <div className="uv-doc-canvas-wrapper" ref={containerRef}>
        <div
          className="uv-preview-container"
          style={{
            transform: `scale(${zoomLevel})`,
            transformOrigin: 'top center',
            transition: 'transform 0.15s ease-out',
            width: isPdf ? '100%' : 'auto',
            height: isPdf ? '100%' : 'auto',
            minHeight: isPdf ? '620px' : 'auto',
          }}
        >
          {isPdf ? (
            <iframe
              src={`${fileUrl}#page=${currentPage}&toolbar=0&navpanes=0`}
              title="Document Preview"
              className="w-full h-full border-none rounded bg-white"
              style={{ minHeight: '620px', minWidth: '480px' }}
            />
          ) : (
            <div className="relative">
              <img
                src={fileUrl}
                alt="Document Evidence"
                className="uv-doc-image"
                onLoad={(e) => {
                  const img = e.target;
                  setCanvasDimensions({ width: img.naturalWidth, height: img.naturalHeight });
                }}
              />
              {/* Bounding Box SVG/Overlay for non-PDF images */}
              {hasValidBbox && (
                <div className="uv-bbox-highlight" style={bboxStyle}>
                  <span className="uv-bbox-label">
                    {activeField?.label || 'Selected Field'}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Interactive Bounding Box Highlight Overlay for PDF canvas */}
          {isPdf && hasValidBbox && (
            <div className="uv-bbox-highlight" style={bboxStyle}>
              <span className="uv-bbox-label">
                {activeField?.label || 'Selected Field'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Drawer: Active Field Evidence Card */}
      {activeField && (
        <div className="uv-evidence-card-drawer">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-slate-100">{activeField.label}</span>
              <span className="font-mono text-xs text-slate-400">({activeField.key})</span>
            </div>

            <div className="flex items-center gap-2">
              {isGrounded ? (
                <span className="uv-badge uv-badge-verified">
                  <CheckCircle2 size={11} /> Grounded
                </span>
              ) : (
                <span className="uv-badge uv-badge-review">
                  <AlertTriangle size={11} /> Ungrounded Quote
                </span>
              )}
              {activeField.evidence?.page && (
                <span className="text-xs text-slate-400 font-mono">
                  Page {activeField.evidence.page}
                </span>
              )}
            </div>
          </div>

          {activeField.evidence?.quote ? (
            <div className="uv-evidence-quote-box">
              "{activeField.evidence.quote}"
            </div>
          ) : (
            <div className="text-xs text-slate-400 italic mt-2">
              No verbatim quote recorded for this field.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
