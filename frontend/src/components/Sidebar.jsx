import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  CheckSquare,
  UploadCloud,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';
import IdpLogo from './IdpLogo';

export default function Sidebar({
  activeTab,
  setActiveTab,
  needsReviewCount = 0,
  collapsed = false,
  onToggleCollapse,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  // Primary Navigation: Dashboard, Documents, Review, Upload
  const primaryNavItems = [
    {
      id: 'dashboard',
      path: '/dashboard',
      label: 'Dashboard',
      icon: LayoutDashboard,
      badge: null,
    },
    {
      id: 'documents',
      path: '/documents',
      label: 'Documents',
      icon: FileText,
      badge: null,
      aliases: ['invoices'],
    },
    {
      id: 'review',
      path: '/review',
      label: 'Review',
      icon: CheckSquare,
      badge: needsReviewCount > 0 ? needsReviewCount : null,
      badgeColor: 'warning',
    },
    {
      id: 'upload',
      path: '/upload',
      label: 'Upload',
      icon: UploadCloud,
      badge: null,
    },
  ];

  const handleNavClick = (item) => {
    navigate(item.path);
    if (setActiveTab) {
      setActiveTab(item.id);
    }
  };

  // Determine current active item from URL pathname or activeTab prop
  const currentSegment = location.pathname.replace(/^\//, '').toLowerCase();

  const isItemActive = (item) => {
    if (activeTab === item.id) return true;
    if (currentSegment === item.id) return true;
    if (location.pathname === item.path) return true;
    if (item.aliases && item.aliases.includes(currentSegment)) return true;
    if (item.id === 'dashboard' && (currentSegment === '' || currentSegment === 'dashboard')) return true;
    return false;
  };

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : 'expanded'}`}>
      {/* 1. App Brand Logo & Collapse Toggle */}
      <div className="sidebar-brand">
        <div className="brand-logo-container">
          <div
            className="brand-logo-wrapper"
            onClick={collapsed ? onToggleCollapse : undefined}
            style={{ cursor: collapsed ? 'pointer' : 'default' }}
            title={collapsed ? 'Click to expand sidebar' : 'IDP - Intelligent Document Processing'}
          >
            <IdpLogo size={34} />
          </div>

          {!collapsed && (
            <div className="brand-text-group">
              <span className="brand-name">IDP</span>
              <span className="brand-tagline">Intelligent Document Processing</span>
            </div>
          )}
        </div>

        {/* Sidebar Inline Toggle Button (visible in expanded mode) */}
        {!collapsed && onToggleCollapse && (
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={onToggleCollapse}
            title="Collapse Sidebar"
            aria-label="Collapse Sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        )}
      </div>

      {/* 2. Navigation Menu */}
      <nav className="sidebar-nav">
        {!collapsed && <div className="nav-section-title">MAIN NAVIGATION</div>}
        <ul className="nav-list">
          {primaryNavItems.map((item) => {
            const Icon = item.icon;
            const active = isItemActive(item);
            return (
              <li key={item.id} className="nav-item">
                <button
                  type="button"
                  id={`nav-${item.id}`}
                  className={`nav-link ${active ? 'active' : ''}`}
                  onClick={() => handleNavClick(item)}
                  title={item.label}
                  aria-label={item.label}
                >
                  <div className="nav-icon-wrapper">
                    <Icon size={19} className="nav-icon" />
                    {collapsed && item.badge !== null && item.badge !== undefined && (
                      <span className="collapsed-badge-dot" title={`${item.badge} pending review`} />
                    )}
                  </div>

                  {!collapsed && <span className="nav-label">{item.label}</span>}

                  {!collapsed && item.badge !== null && item.badge !== undefined && (
                    <span className={`nav-badge ${item.badgeColor || 'primary'}`}>
                      {item.badge}
                    </span>
                  )}

                  {!collapsed && active && <ChevronRight size={14} className="active-arrow" />}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
