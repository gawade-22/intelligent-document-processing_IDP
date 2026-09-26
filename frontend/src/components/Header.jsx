import React from 'react';
import {
  Menu,
  Home,
  ChevronRight,
  Bell,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
} from 'lucide-react';

export default function Header({
  sidebarOpen,
  setSidebarOpen,
  backendConnected = true,
  activeTab = 'dashboard',
  documentId = null,
  onNavigate,
}) {
  const getBreadcrumbTitle = () => {
    switch (activeTab) {
      case 'dashboard':
        return 'Dashboard';
      case 'documents':
      case 'invoices':
        return 'Documents';
      case 'review':
        return 'Review';
      case 'upload':
        return 'Upload';
      case 'reports':
        return 'Reports';
      case 'audit':
        return 'Audit Logs';
      case 'settings':
        return 'Settings';
      case 'document-detail':
        return 'Document Details';
      default:
        return 'Dashboard';
    }
  };

  return (
    <header className="top-header">
      <div className="header-left">
        <button
          type="button"
          className="menu-toggle-btn"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          aria-label="Toggle Sidebar"
          title={sidebarOpen ? 'Collapse Sidebar' : 'Expand Sidebar'}
        >
          <Menu size={20} />
        </button>

        <nav className="breadcrumbs" aria-label="Breadcrumb">
          <span
            className="breadcrumb-home"
            onClick={() => onNavigate && onNavigate('/dashboard')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && onNavigate) onNavigate('/dashboard');
            }}
          >
            <Home size={13} className="breadcrumb-home-icon" />
            <span>Home</span>
          </span>
          <ChevronRight size={12} className="breadcrumb-separator" />
          {activeTab === 'document-detail' ? (
            <>
              <span
                className="breadcrumb-link"
                onClick={() => onNavigate && onNavigate('/documents')}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && onNavigate) onNavigate('/documents');
                }}
              >
                Documents
              </span>
              <ChevronRight size={12} className="breadcrumb-separator" />
              <span className="breadcrumb-current">Document Details</span>
            </>
          ) : (
            <span className="breadcrumb-current">{getBreadcrumbTitle()}</span>
          )}
        </nav>
      </div>

      <div className="header-right">
        {/* API Connectivity status pill */}
        <div
          className={`connectivity-pill ${
            backendConnected ? 'connected' : 'disconnected'
          }`}
          title={
            backendConnected
              ? 'FastAPI Backend Online'
              : 'Backend Disconnected'
          }
        >
          <span className="status-dot" />
          <span className="status-text">
            {backendConnected ? 'API Connected' : 'API Offline'}
          </span>
        </div>

        {/* Notifications */}
        <button
          type="button"
          className="header-icon-btn"
          aria-label="Notifications"
          title="Notifications"
        >
          <Bell size={18} />
          <span className="notification-dot" />
        </button>

        {/* User Pill Dropdown */}
        <div className="header-user-dropdown">
          <div className="header-user-avatar">
            <span>A</span>
          </div>
          <span className="header-user-name">Ayush</span>
          <ChevronDown size={14} className="header-user-caret" />
        </div>
      </div>
    </header>
  );
}
