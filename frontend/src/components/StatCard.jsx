import React from 'react';

/**
 * Reusable StatCard Component
 * Features:
 * - icon with subtle contextual accent tint
 * - small uppercase label
 * - large value with loading skeleton state (no temporary fake numbers)
 * - optional supporting text
 * - compact enterprise layout leaving ample space for tables
 */
export default function StatCard({
  icon: Icon,
  label,
  value,
  supportingText,
  variant = 'blue', // 'blue' | 'green' | 'amber' | 'neutral'
  isLoading = false,
  className = '',
  onClick,
  title,
}) {
  return (
    <div
      className={`stat-card stat-card-${variant} ${onClick ? 'stat-card-clickable' : ''} ${className}`}
      onClick={onClick}
      style={onClick ? { cursor: 'pointer' } : undefined}
      title={title}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); } : undefined}
    >
      <div className="stat-card-inner">
        {Icon && (
          <div className={`stat-card-icon-box icon-variant-${variant}`}>
            <Icon size={20} className="stat-card-icon" />
          </div>
        )}
        <div className="stat-card-body">
          <span className="stat-card-label">{label}</span>

          {isLoading ? (
            <div className="stat-card-skeleton-value" aria-label="Loading metric..." />
          ) : (
            <span className="stat-card-value font-mono">{value}</span>
          )}

          {supportingText && (
            <span className="stat-card-supporting">{supportingText}</span>
          )}
        </div>
      </div>
    </div>
  );
}
