import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  CheckSquare,
  UploadCloud,
  BarChart2,
  Clock,
  Settings,
  ChevronRight,
  ChevronLeft,
  Menu,
  Sparkles,
  FileCode,
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

  // Primary Navigation: Dashboard, Documents, Review, Upload, AI / LLM
  const primaryNavItems = [
    {
      id: 'dashboard',
      path: '/dashboard',
      label: 'Dashboard',
      icon: LayoutDashboard, // home/grid
      badge: null,
    },
    {
      id: 'documents',
      path: '/documents',
      label: 'Documents',
      icon: FileText, // document/list
      badge: null,
      aliases: ['invoices'],
    },
    {
      id: 'review',
      path: '/review',
      label: 'Review',
      icon: CheckSquare, // check/document
      badge: needsReviewCount > 0 ? needsReviewCount : null,
      badgeColor: 'warning',
    },
    {
      id: 'upload',
      path: '/upload',
      label: 'Upload',
      icon: UploadCloud, // upload/cloud
      badge: null,
    },
    {
      id: 'ai-settings',
      path: '/settings/ai',
      label: 'AI / LLM',
      icon: Sparkles, // AI extraction
      badge: null,
      aliases: ['ai-settings', 'ai'],
    },
    {
      id: 'schemas',
      path: '/schemas',
      label: 'Schemas',
      icon: FileCode,
      badge: null,
    },
  ];

  // Secondary Management Tools
  const secondaryNavItems = [
    {
      id: 'reports',
      path: '/reports',
      label: 'Reports',
      icon: BarChart2,
    },
    {
      id: 'audit',
      path: '/audit',
      label: 'Audit Logs',
      icon: Clock,
    },
    {
      id: 'settings',
      path: '/settings',
      label: 'Settings',
      icon: Settings,
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
    if (item.id === 'ai-settings' && (location.pathname.startsWith('/settings/ai') || location.pathname.startsWith('/ai-settings'))) return true;
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

        {/* Secondary Management Links */}
        {!collapsed ? (
          <div className="nav-section-title mt-4">MANAGEMENT</div>
        ) : (
          <div className="nav-divider" title="Management Tools" />
        )}

        <ul className="nav-list">
          {secondaryNavItems.map((item) => {
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
                  </div>
                  {!collapsed && <span className="nav-label">{item.label}</span>}
                  {!collapsed && active && <ChevronRight size={14} className="active-arrow" />}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 3. User Profile Card at Bottom */}
      <div className="sidebar-user">
        <div className="user-card" title="Ayush (VALIDATOR)">
          <div className="user-avatar">
            <span>A</span>
            <span className="online-indicator-dot" />
          </div>
          {!collapsed && (
            <div className="user-info">
              <span className="user-name">Ayush</span>
              <span className="user-role">VALIDATOR</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
