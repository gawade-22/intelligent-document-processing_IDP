import React from 'react';
import {
  Layers,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
} from 'lucide-react';
import StatCard from './StatCard';

export default function StatsCards({ stats = null, isLoading = false, onNavigate }) {
  // Format average confidence percentage
  const formatConfidence = (val) => {
    if (val === null || val === undefined) return '—';
    if (val <= 1.0) {
      return `${Math.round(val * 100)}%`;
    }
    return `${Math.round(val)}%`;
  };

  const isReady = !isLoading && stats !== null;

  return (
    <div className="stats-cards-grid">
      {/* 1. Total Processed -> Blue */}
      <StatCard
        icon={Layers}
        label="TOTAL PROCESSED"
        value={isReady ? stats.total_processed : '—'}
        variant="blue"
        supportingText={isReady ? 'All ingested documents' : 'Loading stats...'}
        isLoading={!isReady}
        onClick={onNavigate ? () => onNavigate('/documents') : undefined}
        title={onNavigate ? 'View all documents' : undefined}
      />

      {/* 2. Total Verified -> Green */}
      <StatCard
        icon={CheckCircle2}
        label="VERIFIED"
        value={isReady ? stats.total_verified : '—'}
        variant="green"
        supportingText={isReady ? 'Approved extractions' : 'Loading stats...'}
        isLoading={!isReady}
        onClick={onNavigate ? () => onNavigate('/documents') : undefined}
        title={onNavigate ? 'View verified documents' : undefined}
      />

      {/* 3. Needs Review -> Amber / Orange */}
      <StatCard
        icon={AlertCircle}
        label="NEEDS REVIEW"
        value={isReady ? stats.total_needing_review : '—'}
        variant="amber"
        supportingText={
          isReady
            ? stats.total_needing_review > 0
              ? 'Click to review queue'
              : 'All clear'
            : 'Loading stats...'
        }
        isLoading={!isReady}
        onClick={onNavigate ? () => onNavigate('/review') : undefined}
        title={onNavigate ? 'Go to Review Queue' : undefined}
      />

      {/* 4. Average Confidence -> Neutral / Blue */}
      <StatCard
        icon={TrendingUp}
        label="AVERAGE CONFIDENCE"
        value={isReady ? formatConfidence(stats.average_confidence) : '—'}
        variant="neutral"
        supportingText={isReady ? 'Target benchmark: ≥ 85%' : 'Loading stats...'}
        isLoading={!isReady}
      />
    </div>
  );
}
