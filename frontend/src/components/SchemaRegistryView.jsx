import React, { useState, useEffect } from 'react';
import {
  FileCode,
  Search,
  Plus,
  RefreshCw,
  Sliders,
  CheckCircle2,
  Calendar,
  Layers,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
} from 'lucide-react';
import { fetchSchemasV2, fetchSchemaDetailV2, createSchemaV2 } from '../services/api';
import SchemaEditor from './dynamic/SchemaEditor';

export default function SchemaRegistryView() {
  const [schemas, setSchemas] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSchemaId, setSelectedSchemaId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newSchemaName, setNewSchemaName] = useState('');
  const [newSchemaFamily, setNewSchemaFamily] = useState('general');
  const [newSchemaDesc, setNewSchemaDesc] = useState('');
  const [toastMsg, setToastMsg] = useState(null);

  const showToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const loadSchemas = async () => {
    setIsLoading(true);
    try {
      const data = await fetchSchemasV2();
      setSchemas(data);
      if (data.length > 0 && !selectedSchemaId) {
        setSelectedSchemaId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load schemas:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadSchemas();
  }, []);

  const handleCreateSchema = async (e) => {
    e.preventDefault();
    if (!newSchemaName.trim()) return;

    try {
      const res = await createSchemaV2({
        name: newSchemaName.trim(),
        family: newSchemaFamily,
        description: newSchemaDesc.trim(),
        schema_definition: {
          sections: ['General Information', 'Line Items'],
          fields: [
            {
              key: 'document_id',
              label: 'Document Identifier',
              data_type: 'id',
              section: 'General Information',
            },
            {
              key: 'document_date',
              label: 'Document Date',
              data_type: 'date',
              section: 'General Information',
            },
          ],
          tables: [],
          validation_rules: [],
          insight_definitions: [],
        },
      });

      showToast(`Schema "${newSchemaName}" registered successfully!`);
      setIsCreating(false);
      setNewSchemaName('');
      setNewSchemaDesc('');
      await loadSchemas();
      setSelectedSchemaId(res.schema_id);
    } catch (err) {
      console.error('Failed to create schema:', err);
      showToast('Failed to create schema.');
    }
  };

  const filteredSchemas = schemas.filter(
    (s) =>
      s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.family.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {toastMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-semibold text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={16} /> {toastMsg}
        </div>
      )}

      {/* Top Banner & Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 bg-white border border-slate-200 rounded-xl shadow-xs">
        <div>
          <h2 className="font-bold text-base text-slate-900 flex items-center gap-2">
            <FileCode size={20} className="text-indigo-600" />
            Universal Schema Registry
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Dynamic schema cache, canonical key bindings, deterministic DSL validation rules, and mathematical insight definitions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold hover:bg-slate-50"
            onClick={loadSchemas}
            disabled={isLoading}
          >
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            className="btn btn-primary btn-sm flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs"
            onClick={() => setIsCreating(true)}
          >
            <Plus size={14} />
            <span>New Custom Schema</span>
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {isCreating && (
        <div className="p-5 bg-white border border-indigo-200 rounded-xl shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-slate-800">Register New Document Schema</h3>
            <button
              type="button"
              className="text-xs text-slate-400 hover:text-slate-600"
              onClick={() => setIsCreating(false)}
            >
              Cancel
            </button>
          </div>

          <form onSubmit={handleCreateSchema} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Schema Name *
              </label>
              <input
                type="text"
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-500"
                placeholder="e.g., Spaceflight Mission Log"
                value={newSchemaName}
                onChange={(e) => setNewSchemaName(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Family Category
              </label>
              <select
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-500 bg-white"
                value={newSchemaFamily}
                onChange={(e) => setNewSchemaFamily(e.target.value)}
              >
                <option value="financial">Financial (Invoices, Receipts, Statements)</option>
                <option value="employment">Employment (Resumes, CVs, Contracts)</option>
                <option value="medical">Medical (Lab Reports, Clinical History)</option>
                <option value="legal">Legal (Agreements, Deeds, Filings)</option>
                <option value="identity">Identity (Passports, IDs, Licenses)</option>
                <option value="academic">Academic (Transcripts, Certificates)</option>
                <option value="tabular">Tabular (Spreadsheets, Multi-Sheet Datasets)</option>
                <option value="logistics">Logistics (Waybills, Challans)</option>
                <option value="general">General / Novel Documents</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Description
              </label>
              <input
                type="text"
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-500"
                placeholder="Optional notes or context"
                value={newSchemaDesc}
                onChange={(e) => setNewSchemaDesc(e.target.value)}
              />
            </div>

            <div className="sm:col-span-3 flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                className="px-4 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                onClick={() => setIsCreating(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg"
              >
                Register Schema
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Two-Column Explorer Layout */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 min-h-[600px]">
        {/* Left Column: Schema List */}
        <div className="md:col-span-4 bg-white border border-slate-200 rounded-xl p-4 flex flex-col space-y-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-500"
              placeholder="Search schemas..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="flex items-center justify-between text-xs text-slate-400 font-medium px-1">
            <span>Registered Schemas</span>
            <span>{filteredSchemas.length} total</span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
            {filteredSchemas.map((s) => {
              const isSelected = selectedSchemaId === s.id;
              return (
                <div
                  key={s.id}
                  className={`p-3 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-50/80 border-indigo-300 shadow-xs'
                      : 'bg-white border-slate-200 hover:bg-slate-50'
                  }`}
                  onClick={() => setSelectedSchemaId(s.id)}
                >
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-xs text-slate-900">{s.name}</h4>
                    <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      v{s.version}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded capitalize bg-slate-100 text-slate-600">
                      {s.family}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {s.origin}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Schema Inspector & Editor */}
        <div className="md:col-span-8 bg-white border border-slate-200 rounded-xl p-6">
          {selectedSchemaId ? (
            <SchemaEditor
              schemaId={selectedSchemaId}
              onReprocessSuccess={loadSchemas}
            />
          ) : (
            <div className="p-12 text-center text-slate-400">
              <FileCode size={40} className="mx-auto mb-2 opacity-50" />
              <p className="font-semibold text-sm">Select a schema to inspect</p>
              <p className="text-xs text-slate-400 mt-1">
                Choose any template or discovered schema on the left to edit its target fields and rules.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
