import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Filter,
  Upload,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Sliders,
  ShieldCheck,
  Cpu,
  ArrowRight,
} from 'lucide-react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import DocumentTable from './components/DocumentTable';
import UploadModal from './components/UploadModal';
import DocumentViewerModal from './components/DocumentViewerModal';
import FilterDrawer from './components/FilterDrawer';
import ReviewQueueView from './components/ReviewQueueView';
import AnalyticsView from './components/AnalyticsView';
import AuditLogView from './components/AuditLogView';
import UploadView from './components/UploadView';
import DocumentDetailsView from './components/ai/DocumentDetailsView';
import AISettings from './pages/AISettings';
import ExtractionAnalyticsPanel from './components/ExtractionAnalyticsPanel';
import SchemaRegistryView from './components/SchemaRegistryView';
import {
  getDashboardStats,
} from './api/dashboard';
import {
  getDocuments,
  getDocumentById,
  getReviewDocuments,
  verifyDocument,
  processDocument,
  deleteDocument,
  batchDeleteDocuments,
} from './api/documents';
import './App.css';

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [detailDocId, setDetailDocId] = useState(null);

  // Documents state
  const [documents, setDocuments] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  // Statistics state
  const [stats, setStats] = useState(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  // Dashboard error state
  const [dashboardError, setDashboardError] = useState(null);

  // Filters & search
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState({
    status: 'ALL',
    documentType: 'ALL',
    vendorName: '',
    invoiceNumber: '',
  });

  // Modals & Drawers
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [isViewerOpen, setIsViewerOpen] = useState(false);

  // Toast / Status notification
  const [toast, setToast] = useState(null);
  const [backendConnected, setBackendConnected] = useState(true);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  // Load summary statistics using GET /api/documents/stats
  const loadStats = useCallback(async () => {
    setIsLoadingStats(true);
    try {
      const data = await getDashboardStats();
      setStats(data);
      setBackendConnected(true);
      setDashboardError(null);
    } catch (err) {
      console.warn('Failed to load stats:', err);
      setBackendConnected(false);
      setDashboardError('Unable to load dashboard data. Please check that the IDP backend is running.');
    } finally {
      setIsLoadingStats(false);
    }
  }, []);

  // Load paginated & filtered documents using GET /api/documents
  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      let effectiveStatus = filters.status;
      if (activeTab === 'review') {
        effectiveStatus = 'NEEDS_REVIEW';
      }

      let effectiveVendor = filters.vendorName;
      let effectiveInvoice = filters.invoiceNumber;
      if (searchTerm.trim()) {
        effectiveVendor = searchTerm.trim();
      }

      const isDash = activeTab === 'dashboard';
      const result = await getDocuments({
        page: isDash ? 1 : page,
        pageSize: isDash ? 10 : pageSize,
        status: effectiveStatus,
        documentType: filters.documentType,
        vendorName: effectiveVendor,
        invoiceNumber: effectiveInvoice,
      });

      setDocuments(result.items || []);
      setTotalCount(result.total || 0);
      setTotalPages(result.total_pages || 1);
      setBackendConnected(true);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setBackendConnected(false);
      setDashboardError('Unable to load dashboard data. Please check that the IDP backend is running.');
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, filters, activeTab, searchTerm]);

  // Initial load: fetch stats & documents
  useEffect(() => {
    loadStats();
    loadDocuments();
  }, [loadStats, loadDocuments]);

  // Synchronize activeTab and detailDocId from React Router location pathname
  useEffect(() => {
    const rawPath = location.pathname.replace(/^\//, '').toLowerCase();
    const docMatch = location.pathname.match(/^\/documents\/([^/]+)$/i);

    if (docMatch) {
      setActiveTab('document-detail');
      setDetailDocId(docMatch[1]);
    } else if (rawPath === '' || rawPath === 'dashboard') {
      setActiveTab('dashboard');
      setDetailDocId(null);
    } else if (rawPath === 'documents' || rawPath === 'invoices') {
      setActiveTab('documents');
      setDetailDocId(null);
    } else if (rawPath === 'review') {
      setActiveTab('review');
      setDetailDocId(null);
    } else if (rawPath === 'upload') {
      setActiveTab('upload');
      setDetailDocId(null);
    } else if (
      rawPath === 'settings/ai' ||
      rawPath === 'ai-settings' ||
      rawPath === 'ai'
    ) {
      setActiveTab('ai-settings');
      setDetailDocId(null);
    } else if (['reports', 'audit', 'settings', 'schemas'].includes(rawPath)) {
      setActiveTab(rawPath);
      setDetailDocId(null);
    }
  }, [location.pathname]);

  // Handle active tab switch
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setDetailDocId(null);
    setPage(1);
    if (tabId === 'ai-settings') {
      navigate('/settings/ai');
    } else {
      navigate(`/${tabId}`);
    }
    if (tabId === 'review') {
      setFilters((prev) => ({ ...prev, status: 'NEEDS_REVIEW' }));
    } else if (tabId === 'documents' || tabId === 'invoices' || tabId === 'dashboard') {
      setFilters((prev) => ({ ...prev, status: 'ALL' }));
    }
  };

  // Quick filter tab handler inside the table
  const handleStatusFilterChange = (newStatus) => {
    setFilters((prev) => ({ ...prev, status: newStatus }));
    setPage(1);
  };

  // Process Document pipeline action
  const handleProcessDocument = async (id) => {
    try {
      showToast(`Initiated automated processing for document #${id}...`, 'info');
      await processDocument(id);
      showToast(`Document #${id} successfully processed!`, 'success');
      loadStats();
      loadDocuments();
    } catch (err) {
      showToast(err.message || `Failed to process document #${id}`, 'error');
    }
  };

  // Batch process documents
  const handleBatchProcess = async (ids) => {
    if (!ids || ids.length === 0) return;
    showToast(`Batch processing ${ids.length} document(s)...`, 'info');
    let successful = 0;
    for (const id of ids) {
      try {
        await processDocument(id);
        successful++;
      } catch (err) {
        console.error(`Batch processing error on #${id}:`, err);
      }
    }
    showToast(`Batch processed ${successful}/${ids.length} documents successfully.`, 'success');
    loadStats();
    loadDocuments();
  };

  // Single document deletion
  const handleDeleteDocument = async (doc) => {
    const docId = doc?.id || doc?.document_id;
    const docName = doc?.file_name || `document #${docId}`;
    if (!window.confirm(`Are you sure you want to permanently delete "${docName}"?\n\nThis will remove the file and all associated extraction records.`)) {
      return;
    }
    try {
      showToast(`Deleting "${docName}"...`, 'info');
      await deleteDocument(docId);
      showToast(`Document "${docName}" deleted successfully!`, 'success');
      loadStats();
      loadDocuments();
    } catch (err) {
      showToast(err.message || `Failed to delete document #${docId}`, 'error');
    }
  };

  // Batch document deletion
  const handleBatchDelete = async (ids, onComplete) => {
    if (!ids || ids.length === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${ids.length} selected document(s)?\n\nThis will permanently remove the files and their extraction records.`)) {
      return;
    }
    try {
      showToast(`Deleting ${ids.length} document(s)...`, 'info');
      const res = await batchDeleteDocuments(ids);
      showToast(res.message || `Deleted ${ids.length} document(s) successfully!`, 'success');
      if (onComplete) onComplete();
      loadStats();
      loadDocuments();
    } catch (err) {
      showToast(err.message || 'Failed to delete selected documents', 'error');
    }
  };

  // Open Document Viewer / Details
  const handleViewDocument = (doc) => {
    const docId = doc.id || doc.document_id;
    navigate(`/documents/${docId}`);
  };

  // Open Document Verification
  const handleVerifyDocument = (doc) => {
    navigate('/review');
  };

  // Filter handlers
  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleResetFilters = () => {
    setFilters({
      status: 'ALL',
      documentType: 'ALL',
      vendorName: '',
      invoiceNumber: '',
    });
    setSearchTerm('');
    setPage(1);
    setIsFilterOpen(false);
  };

  const handleApplyFilters = () => {
    setPage(1);
    setIsFilterOpen(false);
  };

  // Count of active filters
  const activeFilterCount =
    (filters.status !== 'ALL' ? 1 : 0) +
    (filters.documentType !== 'ALL' ? 1 : 0) +
    (filters.vendorName ? 1 : 0) +
    (filters.invoiceNumber ? 1 : 0);

  // Status counts for table tabs
  const statusCounts = {
    ALL: stats?.total_documents ?? totalCount,
    NEEDS_REVIEW: stats?.total_needing_review ?? 0,
    VERIFIED: stats?.total_verified ?? 0,
    PROCESSING: stats?.total_processing ?? 0,
    FAILED: stats?.total_failed ?? 0,
  };

  // Page title and subtitle based on active view
  const getPageHeaderInfo = () => {
    switch (activeTab) {
      case 'dashboard':
        return {
          title: 'Document Processing Dashboard',
          subtitle: 'Monitor document processing, verification, and review status.',
        };
      case 'documents':
      case 'invoices':
        return {
          title: 'Documents',
          subtitle: 'View processing status, verify details, and manage ingested enterprise documents.',
        };
      case 'document-detail':
        return {
          title: 'Document Details',
          subtitle: 'Coming in the next implementation step.',
        };
      case 'review':
        return {
          title: 'Human Review',
          subtitle: 'Coming in the next implementation step.',
        };
      case 'upload':
        return {
          title: 'Upload',
          subtitle: 'Coming in the next implementation step.',
        };
      case 'reports':
        return {
          title: 'Interactive Analytics & Reports',
          subtitle: 'Real-time extraction accuracy, pipeline stage latency, confidence distributions, and format throughput.',
        };
      case 'audit':
        return {
          title: 'Audit & Compliance Logs',
          subtitle: 'Immutable chronological trace of document ingestion, AI reconciliation, human edits, and validation history.',
        };
      case 'settings':
        return {
          title: 'System Settings & Pipeline Configuration',
          subtitle: 'Configure confidence routing thresholds, AI extraction models, OCR fallbacks, and integration endpoints.',
        };
      case 'ai-settings':
        return {
          title: 'AI & LLM',
          subtitle: 'Configure AI-powered document extraction.',
        };
      case 'schemas':
        return {
          title: 'Universal Schema Registry',
          subtitle: 'Dynamic schema definitions, canonical key bindings, deterministic DSL validation rules, and mathematical insights.',
        };
      default:
        return {
          title: 'Document Processing Dashboard',
          subtitle: 'Monitor document processing, verification, and review status.',
        };
    }
  };

  const { title: pageTitle, subtitle: pageSubtitle } = getPageHeaderInfo();

  return (
    <div className={`app-layout ${sidebarOpen ? 'sidebar-expanded' : 'sidebar-collapsed'}`}>
      {/* 1. Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab === 'document-detail' ? 'documents' : activeTab}
        setActiveTab={handleTabChange}
        needsReviewCount={stats?.total_needing_review ?? 0}
        collapsed={!sidebarOpen}
        onToggleCollapse={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* 2. Main Application Wrapper */}
      <div className="main-content-wrapper">
        {/* Top Header */}
        <Header
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          backendConnected={backendConnected}
          activeTab={activeTab}
          documentId={detailDocId}
          onNavigate={(path) => navigate(path)}
        />

        {/* Page Main Content Area */}
        <main className="page-main-container">
          {/* Toast Notification */}
          {toast && (
            <div className={`app-toast toast-${toast.type}`}>
              {toast.type === 'error' ? (
                <AlertCircle size={18} />
              ) : (
                <CheckCircle2 size={18} />
              )}
              <span>{toast.message}</span>
            </div>
          )}

          {/* Page Title & Action Buttons Row */}
          <div className="page-header-row">
            <div className="page-title-group">
              <h1 className="page-title">{pageTitle}</h1>
              <p className="page-subtitle">{pageSubtitle}</p>
            </div>

            <div className="page-actions-group">
              {(activeTab === 'invoices' || activeTab === 'documents' || activeTab === 'dashboard') && (
                <button
                  type="button"
                  className={`btn btn-secondary ${activeFilterCount > 0 ? 'active-filter-btn' : ''}`}
                  onClick={() => {
                    if (activeTab === 'dashboard') {
                      handleTabChange('documents');
                    } else {
                      setIsFilterOpen(true);
                    }
                  }}
                >
                  <Filter size={15} />
                  <span>Advanced Filter</span>
                  {activeFilterCount > 0 && (
                    <span className="filter-count-badge">{activeFilterCount}</span>
                  )}
                </button>
              )}

              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/upload')}
              >
                <Upload size={15} />
                <span>Upload</span>
              </button>

              <button
                type="button"
                className="btn btn-icon"
                onClick={() => {
                  setDashboardError(null);
                  loadStats();
                  loadDocuments();
                }}
                title="Refresh Table & Stats"
                aria-label="Refresh Table & Stats"
              >
                <RefreshCw size={15} className={isLoading || isLoadingStats ? 'spinning' : ''} />
              </button>
            </div>
          </div>

          {/* 3. Conditional View Rendering */}
          {activeTab === 'document-detail' ? (
            <DocumentDetailsView
              docId={detailDocId}
              onBack={() => handleTabChange('documents')}
            />
          ) : activeTab === 'upload' ? (
            <UploadView
              onUploadComplete={() => {
                loadStats();
                loadDocuments();
              }}
              onViewDocument={(id) => navigate(`/documents/${id}`)}
            />
          ) : activeTab === 'review' ? (
            <ReviewQueueView
              onOpenVerify={(id) => {
                setSelectedDocId(id);
                setIsViewerOpen(true);
              }}
              onOpenView={(id) => navigate(`/documents/${id}`)}
            />
          ) : activeTab === 'ai-settings' ? (
            <AISettings />
          ) : activeTab === 'schemas' ? (
            <SchemaRegistryView />
          ) : activeTab === 'reports' ? (
            <AnalyticsView stats={stats} />
          ) : activeTab === 'audit' ? (
            <AuditLogView />
          ) : activeTab === 'settings' ? (
            <div className="settings-panel-card">
              <div className="settings-card-header">
                <div className="settings-icon-circle">
                  <Sliders size={22} className="text-primary" />
                </div>
                <div>
                  <h3 className="settings-header-title">IDP Engine Configuration</h3>
                  <p className="settings-header-sub">Configure automated reconciliation rules, OCR engine preferences, and HITL confidence routing parameters.</p>
                </div>
              </div>
              <div className="settings-grid">
                <div className="settings-item">
                  <label className="settings-label">Confidence Routing Threshold</label>
                  <div className="settings-input-group">
                    <input type="number" defaultValue="85" min="50" max="99" className="settings-input" />
                    <span className="settings-unit">%</span>
                  </div>
                  <span className="settings-hint">Extractions scoring below this threshold are automatically routed to the Human Review Queue.</span>
                </div>

                <div className="settings-item">
                  <label className="settings-label">AI Extraction Model</label>
                  <select defaultValue="gemini-2.5-flash" className="settings-input">
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Production Default)</option>
                    <option value="gemini-1.5-pro">Gemini 1.5 Pro (High Precision)</option>
                    <option value="gpt-4o">GPT-4o Document Intelligence</option>
                  </select>
                  <span className="settings-hint">LLM engine invoked when rule-based extraction confidence is incomplete.</span>
                </div>

                <div className="settings-item">
                  <label className="settings-label">OCR Preprocessing Fallback</label>
                  <select defaultValue="tesseract" className="settings-input">
                    <option value="tesseract">Tesseract OCR (Local, Fast)</option>
                    <option value="easyocr">EasyOCR (Deep Learning)</option>
                    <option value="cloud">Cloud Vision OCR</option>
                  </select>
                  <span className="settings-hint">Used for scanned or image-based invoices with low digital text density.</span>
                </div>

                <div className="settings-item">
                  <label className="settings-label">Maximum Upload Size</label>
                  <div className="settings-input-group">
                    <input type="number" defaultValue="10" min="1" max="50" className="settings-input" />
                    <span className="settings-unit">MB</span>
                  </div>
                  <span className="settings-hint">Hard limit enforced on multi-part file uploads (PDF, PNG, JPG, CSV, XLSX).</span>
                </div>
              </div>

              <div className="settings-actions-footer">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => showToast('Pipeline settings saved successfully!', 'success')}
                >
                  <ShieldCheck size={16} />
                  <span>Save Configuration</span>
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Dashboard Error State if backend unreachable */}
              {dashboardError ? (
                <div className="dashboard-error-state-card" role="alert">
                  <div className="error-icon-box">
                    <AlertCircle size={32} />
                  </div>
                  <h3 className="error-title">Unable to load dashboard data.</h3>
                  <p className="error-description">
                    Please check that the IDP backend is running.
                  </p>
                  <button
                    type="button"
                    className="btn btn-primary btn-retry"
                    onClick={() => {
                      setDashboardError(null);
                      loadStats();
                      loadDocuments();
                    }}
                  >
                    <RefreshCw size={15} />
                    <span>Retry</span>
                  </button>
                </div>
              ) : (
                <>
                  {/* Statistics Cards Grid with loading skeleton state (never fake numbers) */}
                  <StatsCards stats={stats} isLoading={isLoadingStats} />

                  {/* Extraction Record Analytics Panel */}
                  {activeTab === 'dashboard' && (
                    <ExtractionAnalyticsPanel stats={stats} isLoading={isLoadingStats} />
                  )}

                  {/* Document Management Section Header */}
                  <div className="section-header-row">
                    <div className="section-title-group">
                      <h2 className="section-title">
                        {activeTab === 'dashboard' ? 'Recent Documents' : 'Documents'}
                      </h2>
                      <p className="section-subtitle">
                        {activeTab === 'dashboard'
                          ? 'Live multi-format documents recently ingested and processed'
                          : 'Complete document archive with advanced filtering and batch operations'}
                      </p>
                    </div>

                    {activeTab === 'dashboard' && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTabChange('documents')}
                        title="View All Documents in Archive"
                      >
                        <span>View All</span>
                        <ArrowRight size={14} />
                      </button>
                    )}
                  </div>

                  {/* Professional Document Data Table */}
                  <DocumentTable
                    documents={documents}
                    total={totalCount}
                    page={page}
                    pageSize={pageSize}
                    totalPages={totalPages}
                    onPageChange={(newPage) => setPage(newPage)}
                    onPageSizeChange={(newSize) => {
                      setPageSize(newSize);
                      setPage(1);
                    }}
                    searchTerm={searchTerm}
                    onSearchChange={(term) => {
                      setSearchTerm(term);
                      setPage(1);
                    }}
                    currentStatusFilter={filters.status}
                    onAdvancedFilter={() => {
                      if (activeTab === 'dashboard') {
                        handleTabChange('documents');
                      } else {
                        setIsFilterOpen(true);
                      }
                    }}
                    onUploadClick={() => navigate('/upload')}
                    isDashboard={activeTab === 'dashboard'}
                    onViewDetails={(id) => navigate(`/documents/${id}`)}
                    onReviewDocument={() => navigate('/review')}
                    onViewDocument={(doc) => navigate(`/documents/${doc.id || doc.document_id}`)}
                    onDeleteDocument={handleDeleteDocument}
                    onBatchDelete={handleBatchDelete}
                    isLoading={isLoading}
                    statusCounts={statusCounts}
                  />
                </>
              )}
            </>
          )}
        </main>
      </div>

      {/* 5. Upload Modal */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadSuccess={() => {
          showToast('Document uploaded successfully!', 'success');
          loadStats();
          loadDocuments();
        }}
      />

      {/* 6. Document Viewer & Verification Modal */}
      <DocumentViewerModal
        docId={selectedDocId}
        isOpen={isViewerOpen}
        onClose={() => {
          setIsViewerOpen(false);
          setSelectedDocId(null);
        }}
        onUpdateSuccess={() => {
          showToast('Verification record updated successfully!', 'success');
          loadStats();
          loadDocuments();
        }}
      />

      {/* 7. Advanced Filter Drawer */}
      <FilterDrawer
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        filters={filters}
        onFilterChange={handleFilterChange}
        onResetFilters={handleResetFilters}
        onApplyFilters={handleApplyFilters}
      />
    </div>
  );
}
