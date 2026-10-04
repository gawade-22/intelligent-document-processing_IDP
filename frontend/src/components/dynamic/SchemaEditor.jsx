import React, { useState, useEffect } from 'react';
import {
  FileCode,
  Save,
  RefreshCw,
  Plus,
  Trash2,
  Edit2,
  Check,
  X,
  Layers,
  Sparkles,
  Info,
  CheckCircle2,
} from 'lucide-react';
import { fetchSchemaDetailV2, updateSchemaV2, reprocessDocumentV2 } from '../../services/api';

const DATA_TYPES = [
  'string',
  'number',
  'date',
  'money',
  'percent',
  'email',
  'phone',
  'id',
  'text',
  'bool',
];

export default function SchemaEditor({
  schemaId,
  documentId,
  onReprocessSuccess,
}) {
  const [schema, setSchema] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // New field form state
  const [newKey, setNewKey] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newDataType, setNewDataType] = useState('string');
  const [newSection, setNewSection] = useState('General Information');

  useEffect(() => {
    async function loadSchema() {
      if (!schemaId) return;
      setIsLoading(true);
      try {
        const data = await fetchSchemaDetailV2(schemaId);
        setSchema(data);
      } catch (err) {
        setErrorMsg(err.message || 'Failed to load schema definition.');
      } finally {
        setIsLoading(false);
      }
    }
    loadSchema();
  }, [schemaId]);

  if (isLoading) {
    return (
      <div className="p-10 text-center text-slate-400">
        <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-blue-500" />
        <p className="text-xs">Loading registered schema definition...</p>
      </div>
    );
  }

  if (!schema) {
    return (
      <div className="p-8 text-center text-slate-400 bg-white border border-slate-200 rounded-xl">
        <FileCode size={36} className="mx-auto mb-2 opacity-50" />
        <p className="font-semibold text-sm">Schema Not Available</p>
        <p className="text-xs mt-1">No schema was resolved for this document yet.</p>
      </div>
    );
  }

  const definition = schema.definition || {};
  const fields = definition.fields || [];
  const sections = definition.sections || ['General Information'];

  const handleAddField = () => {
    if (!newKey.trim()) return;
    const cleanKey = newKey.toLowerCase().replace(/[^a-z0-9_]/g, '_').trim();
    const cleanLabel = newLabel.trim() || cleanKey.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

    const updatedFields = [
      ...fields,
      {
        key: cleanKey,
        label: cleanLabel,
        data_type: newDataType,
        section: newSection,
      },
    ];

    const updatedSections = sections.includes(newSection) ? sections : [...sections, newSection];

    setSchema((prev) => ({
      ...prev,
      definition: {
        ...prev.definition,
        fields: updatedFields,
        sections: updatedSections,
      },
    }));

    setNewKey('');
    setNewLabel('');
  };

  const handleRemoveField = (fieldKey) => {
    const updatedFields = fields.filter((f) => f.key !== fieldKey);
    setSchema((prev) => ({
      ...prev,
      definition: {
        ...prev.definition,
        fields: updatedFields,
      },
    }));
  };

  const handleSaveSchema = async (andReprocess = false) => {
    setIsSaving(true);
    setErrorMsg(null);
    setSaveSuccess(false);

    try {
      await updateSchemaV2(schema.id, {
        name: schema.name,
        family: schema.family,
        description: schema.description,
        schema_definition: schema.definition,
      });

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);

      if (andReprocess && documentId) {
        setIsReprocessing(true);
        await reprocessDocumentV2(documentId);
        if (onReprocessSuccess) onReprocessSuccess();
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to save schema.');
    } finally {
      setIsSaving(false);
      setIsReprocessing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Schema Header */}
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-xs">
            <FileCode size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-sm text-slate-900">{schema.name}</h3>
              <span className="uv-badge uv-badge-primary">v{schema.version}</span>
              <span className="uv-badge uv-badge-family">{schema.origin}</span>
            </div>
            <p className="text-xs text-slate-500 font-mono mt-0.5">{schema.id}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold hover:bg-slate-100"
            onClick={() => handleSaveSchema(false)}
            disabled={isSaving}
          >
            <Save size={14} />
            <span>{isSaving ? 'Saving...' : 'Save Schema'}</span>
          </button>

          {documentId && (
            <button
              type="button"
              className="btn btn-primary btn-sm flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold"
              onClick={() => handleSaveSchema(true)}
              disabled={isSaving || isReprocessing}
            >
              <RefreshCw size={14} className={isReprocessing ? 'animate-spin' : ''} />
              <span>{isReprocessing ? 'Reprocessing...' : 'Save & Re-Extract'}</span>
            </button>
          )}
        </div>
      </div>

      {saveSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-semibold text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={15} /> Schema successfully saved and updated in Registry!
        </div>
      )}

      {errorMsg && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs font-semibold text-red-800">
          {errorMsg}
        </div>
      )}

      {/* Add New Field Form */}
      <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3">
        <h4 className="font-bold text-xs uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <Plus size={14} /> Add Target Field to Schema
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">Field Key</label>
            <input
              type="text"
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-md focus:outline-none focus:border-blue-500 font-mono"
              placeholder="e.g., project_budget"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">Display Label</label>
            <input
              type="text"
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-md focus:outline-none focus:border-blue-500"
              placeholder="e.g., Project Budget"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">Data Type</label>
            <select
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-md focus:outline-none focus:border-blue-500 bg-white"
              value={newDataType}
              onChange={(e) => setNewDataType(e.target.value)}
            >
              {DATA_TYPES.map((dt) => (
                <option key={dt} value={dt}>
                  {dt}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">Section</label>
            <input
              type="text"
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-md focus:outline-none focus:border-blue-500"
              placeholder="Section Name"
              value={newSection}
              onChange={(e) => setNewSection(e.target.value)}
            />
          </div>
        </div>

        <button
          type="button"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold mt-1"
          onClick={handleAddField}
        >
          <Plus size={13} /> Add Field
        </button>
      </div>

      {/* Fields List */}
      <div className="space-y-2">
        <h4 className="font-bold text-xs uppercase tracking-wider text-slate-500">
          Target Schema Fields ({fields.length})
        </h4>

        <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase">
              <tr>
                <th className="py-2.5 px-3">Field Key</th>
                <th className="py-2.5 px-3">Label</th>
                <th className="py-2.5 px-3">Data Type</th>
                <th className="py-2.5 px-3">Section</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {fields.map((f, idx) => (
                <tr key={idx} className="hover:bg-slate-50">
                  <td className="py-2 px-3 font-mono font-semibold text-slate-800">{f.key}</td>
                  <td className="py-2 px-3 text-slate-700">{f.label}</td>
                  <td className="py-2 px-3">
                    <span className="uv-field-type-tag">{f.data_type}</span>
                  </td>
                  <td className="py-2 px-3 text-slate-600">{f.section || 'General'}</td>
                  <td className="py-2 px-3 text-right">
                    <button
                      type="button"
                      className="p-1 text-slate-400 hover:text-red-600 rounded hover:bg-red-50"
                      onClick={() => handleRemoveField(f.key)}
                      title="Remove field"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
