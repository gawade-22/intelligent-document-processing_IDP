import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Filter,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import DocumentTable from './components/DocumentTable';
import DocumentViewerModal from './components/DocumentViewerModal';
import FilterDrawer from './components/FilterDrawer';
import ReviewQueueView from './components/ReviewQueueView';
import UploadView from './components/UploadView';
import DocumentDetailsView from './components/ai/DocumentDetailsView';
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
      setDashboardError(null);
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
    } else {
      setActiveTab('dashboard');
      setDetailDocId(null);
    }
  }, [location.pathname]);

  // Handle active tab switch
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setDetailDocId(null);
    setPage(1);
    navigate(`/${tabId}`);
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
          subtitle: 'Inspect document preview, extracted fields, and processing runs.',
        };
      case 'review':
        return {
          title: 'Human Review',
          subtitle: 'Verify and approve extracted document data.',
        };
      case 'upload':
        return {
          title: 'Upload Document',
          subtitle: 'Ingest and process documents with automated OCR and extraction.',
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
              {(activeTab === 'invoices' || activeTab === 'documents') && (
                <button
                  type="button"
                  className={`btn btn-secondary ${activeFilterCount > 0 ? 'active-filter-btn' : ''}`}
                  onClick={() => setIsFilterOpen(true)}
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
                  <StatsCards
                    stats={stats}
                    isLoading={isLoadingStats}
                    onNavigate={(path) => navigate(path)}
                  />

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

      {/* Document Viewer & Verification Modal */}
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
