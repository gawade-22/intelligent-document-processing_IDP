import React, { useState } from 'react';
import {
  MapPin,
  CheckCircle2,
  AlertTriangle,
  Edit2,
  Check,
  X,
  Layers,
  ExternalLink,
  ShieldCheck,
  Copy,
  Hash,
  Calendar,
  DollarSign,
  Percent,
  Mail,
  Phone,
  FileText,
  ToggleRight,
  Briefcase,
  GraduationCap,
  FolderGit2,
  Code2,
} from 'lucide-react';

/**
 * Returns typed icon based on schema data_type and field key.
 */
function getTypeIcon(dataType, key = '') {
  const normKey = key.toLowerCase();
  if (normKey.includes('skill')) return <Code2 size={13} className="text-amber-600" />;
  if (normKey.includes('experience') || normKey.includes('job')) return <Briefcase size={13} className="text-indigo-600" />;
  if (normKey.includes('education') || normKey.includes('degree')) return <GraduationCap size={13} className="text-emerald-600" />;
  if (normKey.includes('project')) return <FolderGit2 size={13} className="text-cyan-600" />;

  switch (dataType) {
    case 'money':
      return <DollarSign size={13} className="text-emerald-600" />;
    case 'date':
      return <Calendar size={13} className="text-blue-600" />;
    case 'percent':
      return <Percent size={13} className="text-purple-600" />;
    case 'email':
      return <Mail size={13} className="text-sky-600" />;
    case 'phone':
      return <Phone size={13} className="text-indigo-600" />;
    case 'id':
      return <Hash size={13} className="text-amber-600" />;
    case 'bool':
      return <ToggleRight size={13} className="text-teal-600" />;
    default:
      return <FileText size={13} className="text-slate-500" />;
  }
}

/**
 * Render structured skill badges from multiline or comma-separated text.
 */
function renderSkillsLayout(strVal) {
  const lines = strVal.split('\n').filter(l => l.trim().length > 0);
  return (
    <div className="uv-skills-canvas">
      {lines.map((line, lIdx) => {
        if (line.includes(':')) {
          const [category, items] = line.split(/:(.+)/);
          const skillPills = (items || '')
            .split(/[,|]/)
            .map(s => s.trim())
            .filter(s => s.length > 0);

          return (
            <div key={lIdx} className="uv-skill-category-row">
              <span className="uv-skill-category-label">{category.trim()}:</span>
              <div className="uv-skill-pills-wrap">
                {skillPills.map((pill, pIdx) => (
                  <span key={pIdx} className="uv-skill-pill">
                    {pill}
                  </span>
                ))}
              </div>
            </div>
          );
        }

        // Just items
        const pills = line.split(/[,|]/).map(s => s.trim()).filter(s => s.length > 0);
        return (
          <div key={lIdx} className="uv-skill-pills-wrap">
            {pills.map((pill, pIdx) => (
              <span key={pIdx} className="uv-skill-pill">
                {pill}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Render structured bullet points and sub-sections for experience/projects/education.
 */
function renderStructuredContent(strVal) {
  const lines = strVal.split('\n').filter(l => l.trim().length > 0);
  return (
    <div className="uv-structured-canvas">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        const isBullet = trimmed.startsWith('•') || trimmed.startsWith('-') || trimmed.startsWith('*') || /^\d+\./.test(trimmed);
        const cleanLine = trimmed.replace(/^[•\-\*]\s*/, '');

        if (isBullet) {
          return (
            <div key={idx} className="uv-canvas-bullet-item">
              <span className="uv-canvas-bullet-dot">•</span>
              <span className="uv-canvas-bullet-text">{cleanLine}</span>
            </div>
          );
        }

        // Potential title or subtitle
        const isHeader = idx === 0 || trimmed.length < 50;
        return (
          <div
            key={idx}
            className={isHeader ? 'uv-canvas-item-heading' : 'uv-canvas-item-paragraph'}
          >
            {trimmed}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Formats display value according to data_type and content structure.
 */
function formatDisplayValue(val, dataType, key = '', label = '') {
  if (val === null || val === undefined || val === '') {
    return <span className="uv-field-value null-val">Not Detected</span>;
  }

  const strVal = String(val).trim();
  const normKey = (key + ' ' + label).toLowerCase();

  // 1. Technical Skills special canvas
  if (normKey.includes('skill')) {
    return renderSkillsLayout(strVal);
  }

  // 2. Multiline Experience / Projects / Education
  if (
    strVal.includes('\n') &&
    (normKey.includes('experience') || normKey.includes('project') || normKey.includes('education') || normKey.includes('summary'))
  ) {
    if (normKey.includes('summary')) {
      return (
        <div className="uv-summary-canvas">
          <p className="uv-summary-text">{strVal}</p>
        </div>
      );
    }
    return renderStructuredContent(strVal);
  }

  // 3. Multiline generic text
  if (strVal.includes('\n')) {
    return (
      <div className="uv-multiline-text">
        {strVal.split('\n').map((l, i) => (
          <p key={i}>{l}</p>
        ))}
      </div>
    );
  }

  // 4. Standard typed fields
  switch (dataType) {
    case 'money':
      return <span className="uv-field-value money-val">{strVal}</span>;
    case 'date':
      return <span className="uv-field-value date-val">{strVal}</span>;
    case 'id':
      return (
        <code className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 font-mono text-xs">
          {strVal}
        </code>
      );
    case 'email':
      return (
        <a
          href={`mailto:${strVal}`}
          className="text-blue-600 hover:underline flex items-center gap-1 font-medium"
          target="_blank"
          rel="noreferrer"
        >
          {strVal}
          <ExternalLink size={11} />
        </a>
      );
    case 'phone':
      return (
        <a
          href={`tel:${strVal}`}
          className="text-indigo-600 hover:underline flex items-center gap-1 font-medium"
        >
          {strVal}
        </a>
      );
    case 'bool':
      return (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${
            strVal.toLowerCase() === 'true' || strVal === '1'
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-slate-100 text-slate-700'
          }`}
        >
          {strVal.toLowerCase() === 'true' || strVal === '1' ? 'YES' : 'NO'}
        </span>
      );
    default:
      if (strVal.startsWith('http://') || strVal.startsWith('https://')) {
        return (
          <a
            href={strVal}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 hover:underline flex items-center gap-1 break-all font-medium"
          >
            {strVal}
            <ExternalLink size={11} className="flex-shrink-0" />
          </a>
        );
      }
      return <span className="uv-field-value">{strVal}</span>;
  }
}

export default function DynamicFieldWidget({
  field,
  isActive = false,
  onSelectEvidence,
  onUpdateField,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(field.normalized_value || field.value || '');
  const [showPasses, setShowPasses] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const confScore = Math.round((field.confidence || 0) * 100);
  const confClass =
    confScore >= 85 ? 'uv-conf-high' : confScore >= 60 ? 'uv-conf-med' : 'uv-conf-low';

  const isGrounded = field.evidence?.grounded ?? false;
  const passes = field.passes || [];
  const hasMultiplePasses = passes.length > 1;

  const strVal = String(field.normalized_value || field.value || '');
  const normKey = ((field.key || '') + ' ' + (field.label || '')).toLowerCase();
  const isMultilineField =
    strVal.includes('\n') ||
    strVal.length > 80 ||
    ['summary', 'skills', 'experience', 'projects', 'education'].some(k => normKey.includes(k));

  const handleCopy = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(strVal);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveEdit = async () => {
    if (editValue === field.value && editValue === field.normalized_value) {
      setIsEditing(false);
      return;
    }
    setIsSaving(true);
    try {
      if (onUpdateField) {
        await onUpdateField(field.id || field.key, editValue);
      }
      setIsEditing(false);
    } catch (err) {
      console.error('Failed to update field:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleAcceptPass = async (candidateVal) => {
    setEditValue(candidateVal);
    if (onUpdateField) {
      await onUpdateField(field.id || field.key, candidateVal);
    }
    setShowPasses(false);
  };

  return (
    <div
      className={`uv-field-card ${isMultilineField ? 'uv-field-card-full' : ''} ${
        isActive ? 'active-highlight' : ''
      } ${field.status === 'needs_review' ? 'needs-review-card' : ''}`}
      onClick={() => onSelectEvidence && onSelectEvidence(field)}
    >
      {/* Top Header: Label, Type Tag & Confidence Meter */}
      <div className="uv-field-header">
        <span className="uv-field-label" title={field.label}>
          {getTypeIcon(field.data_type, field.key || field.label)}
          <span>{field.label}</span>
        </span>

        <div className="flex items-center gap-1.5">
          <span className={`uv-conf-pill ${confClass}`} title={`Calibrated Confidence: ${confScore}%`}>
            <ShieldCheck size={10} />
            {confScore}%
          </span>
          <span className="uv-field-type-tag">{field.data_type}</span>
        </div>
      </div>

      {/* Canonical Key & Grounding indicator */}
      <div className="uv-field-meta-row">
        <span className="uv-field-canonical-key" title={`Canonical key: ${field.key}`}>
          {field.key}
        </span>
        {isGrounded ? (
          <span
            className="uv-grounded-tag"
            title="Evidence verified and located on document"
            onClick={(e) => {
              e.stopPropagation();
              onSelectEvidence && onSelectEvidence(field);
            }}
          >
            <MapPin size={10} /> Grounded
          </span>
        ) : (
          <span
            className="uv-ungrounded-tag"
            title="Ungrounded value: evidence quote not located in source"
          >
            <AlertTriangle size={10} /> Ungrounded
          </span>
        )}
      </div>

      {/* Field Value Display or Inline Editor */}
      <div className="uv-field-value-row" onClick={(e) => isEditing && e.stopPropagation()}>
        {isEditing ? (
          <div className="uv-inline-edit-wrapper">
            {isMultilineField ? (
              <textarea
                rows={Math.min(10, Math.max(4, (editValue || '').split('\n').length + 1))}
                className="uv-inline-textarea"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                autoFocus
              />
            ) : (
              <input
                type="text"
                className="uv-inline-input"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveEdit();
                  if (e.key === 'Escape') setIsEditing(false);
                }}
                autoFocus
              />
            )}

            <div className="uv-inline-edit-actions">
              <button
                type="button"
                className="uv-btn-save-field"
                onClick={handleSaveEdit}
                disabled={isSaving}
                title="Save changes"
              >
                <Check size={13} />
                <span>{isSaving ? 'Saving...' : 'Save'}</span>
              </button>
              <button
                type="button"
                className="uv-btn-cancel-field"
                onClick={() => setIsEditing(false)}
                title="Cancel editing"
              >
                <X size={13} />
                <span>Cancel</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="uv-field-content-container">
            <div className="uv-field-display-body">
              {formatDisplayValue(field.normalized_value || field.value, field.data_type, field.key, field.label)}
            </div>

            <div className="uv-field-action-bar" onClick={(e) => e.stopPropagation()}>
              {strVal && (
                <button
                  type="button"
                  className="uv-field-action-btn"
                  onClick={handleCopy}
                  title={copied ? 'Copied to clipboard!' : 'Copy value'}
                >
                  {copied ? <CheckCircle2 size={13} className="text-emerald-600" /> : <Copy size={13} />}
                </button>
              )}

              {hasMultiplePasses && (
                <button
                  type="button"
                  className="uv-field-action-btn"
                  onClick={() => setShowPasses(!showPasses)}
                  title="Compare multi-pass candidate values"
                >
                  <Layers size={13} />
                </button>
              )}

              <button
                type="button"
                className="uv-field-action-btn uv-edit-action-btn"
                onClick={() => {
                  setEditValue(field.normalized_value || field.value || '');
                  setIsEditing(true);
                }}
                title="Edit extracted value"
              >
                <Edit2 size={13} />
                <span className="text-[11px] font-medium ml-1">Edit</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Validation Messages / DSL Warnings */}
      {field.validation?.messages?.length > 0 && (
        <div className="uv-field-warn-msg mt-2">
          <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{field.validation.messages.join(' ')}</span>
        </div>
      )}

      {/* Multi-Pass Candidate Drawer */}
      {showPasses && (
        <div
          className="mt-2.5 pt-2 border-t border-slate-200 bg-slate-50 -mx-3.5 -mb-3 p-3 rounded-b-lg text-xs"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between font-semibold text-slate-600 mb-1.5">
            <span>Extraction Pass Candidates ({passes.length})</span>
            <button
              type="button"
              className="text-slate-400 hover:text-slate-600"
              onClick={() => setShowPasses(false)}
            >
              <X size={12} />
            </button>
          </div>

          <div className="space-y-1.5">
            {passes.map((p, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-1.5 rounded bg-white border border-slate-200"
              >
                <div>
                  <span className="font-semibold text-[10px] text-slate-500 uppercase mr-1.5">
                    {p.engine}:
                  </span>
                  <span className="font-mono text-xs text-slate-900">{String(p.value)}</span>
                </div>
                <button
                  type="button"
                  className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100"
                  onClick={() => handleAcceptPass(p.value)}
                >
                  Accept
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
