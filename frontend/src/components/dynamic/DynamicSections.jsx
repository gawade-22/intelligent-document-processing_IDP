import React, { useState, useMemo } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Search,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
  Plus,
  LayoutGrid,
  Table as TableIcon,
  X,
  Check,
  Sparkles,
} from 'lucide-react';
import DynamicFieldWidget from './DynamicFieldWidget';

export default function DynamicSections({
  sections = [],
  fields = [],
  activeFieldId = null,
  onSelectEvidence,
  onUpdateField,
  onAddField,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [collapsedSections, setCollapsedSections] = useState({});
  const [viewMode, setViewMode] = useState('canvas'); // 'canvas' | 'table'
  const [isAddingField, setIsAddingField] = useState(false);
  const [newFieldLabel, setNewFieldLabel] = useState('');
  const [newFieldSection, setNewFieldSection] = useState('');
  const [newFieldType, setNewFieldType] = useState('string');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [isSubmittingNewField, setIsSubmittingNewField] = useState(false);

  const toggleSection = (sectionName) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionName]: !prev[sectionName],
    }));
  };

  // Group fields dynamically by section
  const { groupedFields, activeSectionList } = useMemo(() => {
    const groups = {};
    const sectionOrder = [...sections];

    fields.forEach((f) => {
      const sec = f.section || 'General Information';
      if (!groups[sec]) {
        groups[sec] = [];
        if (!sectionOrder.includes(sec)) {
          sectionOrder.push(sec);
        }
      }
      groups[sec].push(f);
    });

    return {
      groupedFields: groups,
      activeSectionList: sectionOrder.filter((s) => groups[s] && groups[s].length > 0),
    };
  }, [sections, fields]);

  // Filter fields based on search term
  const filteredGroups = useMemo(() => {
    if (!searchTerm.trim()) return groupedFields;

    const query = searchTerm.toLowerCase().trim();
    const result = {};

    Object.entries(groupedFields).forEach(([sec, secFields]) => {
      const matching = secFields.filter(
        (f) =>
          f.label.toLowerCase().includes(query) ||
          f.key.toLowerCase().includes(query) ||
          String(f.value || '').toLowerCase().includes(query)
      );
      if (matching.length > 0) {
        result[sec] = matching;
      }
    });

    return result;
  }, [groupedFields, searchTerm]);

  const handleOpenAddField = (defaultSection = '') => {
    setNewFieldSection(defaultSection || activeSectionList[0] || 'General');
    setNewFieldLabel('');
    setNewFieldValue('');
    setNewFieldType('string');
    setIsAddingField(true);
  };

  const handleSaveNewField = async (e) => {
    e.preventDefault();
    if (!newFieldLabel.trim()) return;

    setIsSubmittingNewField(true);
    try {
      if (onAddField) {
        await onAddField({
          label: newFieldLabel.trim(),
          section: newFieldSection.trim() || 'General',
          data_type: newFieldType,
          value: newFieldValue.trim(),
        });
      }
      setIsAddingField(false);
      setNewFieldLabel('');
      setNewFieldValue('');
    } catch (err) {
      console.error('Failed to create field:', err);
    } finally {
      setIsSubmittingNewField(false);
    }
  };

  return (
    <div className="dynamic-sections-container">
      {/* Search, Filter & Add Header */}
      <div className="uv-search-filter-bar">
        <div className="uv-search-wrapper">
          <Search size={14} className="uv-search-icon" />
          <input
            type="text"
            className="uv-search-input"
            placeholder="Search fields by name, canonical key, or value..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="uv-controls-group">
          {/* View mode toggle */}
          <div className="uv-view-mode-toggle">
            <button
              type="button"
              className={`uv-toggle-btn ${viewMode === 'canvas' ? 'active' : ''}`}
              onClick={() => setViewMode('canvas')}
              title="Canvas & Cards Layout"
            >
              <LayoutGrid size={13} />
              <span>Canvas</span>
            </button>
            <button
              type="button"
              className={`uv-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Compact Table Layout"
            >
              <TableIcon size={13} />
              <span>Table</span>
            </button>
          </div>

          {/* Add Field Button */}
          <button
            type="button"
            className="uv-add-field-btn"
            onClick={() => handleOpenAddField()}
            title="Manually add a field if missing from extraction"
          >
            <Plus size={13} />
            <span>Add Field</span>
          </button>
        </div>
      </div>

      {/* Add Custom Field Inline Card */}
      {isAddingField && (
        <form className="uv-add-field-card animate-fadeIn" onSubmit={handleSaveNewField}>
          <div className="uv-add-field-header">
            <div className="flex items-center gap-2">
              <Sparkles size={14} className="text-blue-600" />
              <span className="font-bold text-xs text-slate-800">Add Custom Extracted Field</span>
            </div>
            <button
              type="button"
              className="text-slate-400 hover:text-slate-600"
              onClick={() => setIsAddingField(false)}
            >
              <X size={14} />
            </button>
          </div>

          <div className="uv-add-field-grid">
            <div>
              <label className="uv-form-label">Field Name / Label *</label>
              <input
                type="text"
                className="uv-form-input"
                placeholder="e.g. LinkedIn Profile, CGPA, Due Date"
                value={newFieldLabel}
                onChange={(e) => setNewFieldLabel(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div>
              <label className="uv-form-label">Target Section</label>
              <input
                type="text"
                className="uv-form-input"
                list="sections-datalist"
                placeholder="e.g. Personal Details, Summary"
                value={newFieldSection}
                onChange={(e) => setNewFieldSection(e.target.value)}
              />
              <datalist id="sections-datalist">
                {activeSectionList.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </div>

            <div>
              <label className="uv-form-label">Data Type</label>
              <select
                className="uv-form-select"
                value={newFieldType}
                onChange={(e) => setNewFieldType(e.target.value)}
              >
                <option value="string">Text / String</option>
                <option value="date">Date</option>
                <option value="money">Currency / Money</option>
                <option value="email">Email</option>
                <option value="phone">Phone</option>
                <option value="number">Number</option>
              </select>
            </div>
          </div>

          <div className="mt-3">
            <label className="uv-form-label">Field Value *</label>
            <textarea
              rows={3}
              className="uv-form-textarea"
              placeholder="Enter verbatim or extracted value..."
              value={newFieldValue}
              onChange={(e) => setNewFieldValue(e.target.value)}
              required
            />
          </div>

          <div className="uv-add-field-actions">
            <button
              type="submit"
              className="uv-btn uv-btn-primary"
              disabled={isSubmittingNewField || !newFieldLabel.trim()}
            >
              <Check size={13} />
              <span>{isSubmittingNewField ? 'Adding Field...' : 'Add Field'}</span>
            </button>
            <button
              type="button"
              className="uv-btn uv-btn-secondary"
              onClick={() => setIsAddingField(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Dynamic Section Cards */}
      {activeSectionList.length === 0 ? (
        <div className="p-8 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
          <FolderOpen size={36} className="mx-auto mb-2 opacity-50 text-slate-400" />
          <p className="font-semibold text-sm text-slate-600">No fields extracted</p>
          <p className="text-xs text-slate-400 mt-1">
            This document schema did not produce any extracted fields.
          </p>
          <button
            type="button"
            className="uv-btn uv-btn-primary mt-3 mx-auto"
            onClick={() => handleOpenAddField()}
          >
            <Plus size={13} />
            <span>Add First Field</span>
          </button>
        </div>
      ) : (
        activeSectionList.map((sectionName) => {
          const sectionFields = filteredGroups[sectionName] || [];
          if (searchTerm && sectionFields.length === 0) return null;

          const isCollapsed = collapsedSections[sectionName];
          const reviewCount = sectionFields.filter((f) => f.status === 'needs_review').length;

          return (
            <div key={sectionName} className="uv-section-card">
              <div
                className="uv-section-header"
                onClick={() => toggleSection(sectionName)}
              >
                <div className="uv-section-title">
                  {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                  <span>{sectionName}</span>
                  <span className="uv-section-count">
                    ({sectionFields.length})
                  </span>
                </div>

                <div className="uv-section-badges">
                  <button
                    type="button"
                    className="uv-quick-add-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenAddField(sectionName);
                    }}
                    title={`Add new field to ${sectionName}`}
                  >
                    <Plus size={11} />
                    <span>Add</span>
                  </button>

                  {reviewCount > 0 ? (
                    <span className="uv-badge uv-badge-review">
                      <AlertCircle size={11} /> {reviewCount} Review
                    </span>
                  ) : (
                    <span className="uv-badge uv-badge-verified">
                      <CheckCircle2 size={11} /> Verified
                    </span>
                  )}
                </div>
              </div>

              {!isCollapsed && (
                <div className={viewMode === 'canvas' ? 'uv-field-grid uv-canvas-grid' : 'uv-field-table-view'}>
                  {sectionFields.map((field) => (
                    <DynamicFieldWidget
                      key={field.id || field.key}
                      field={field}
                      isActive={activeFieldId === field.id || activeFieldId === field.key}
                      onSelectEvidence={onSelectEvidence}
                      onUpdateField={onUpdateField}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
