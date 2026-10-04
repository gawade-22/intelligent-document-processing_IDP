import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Check,
  Edit2,
  Layers,
  MapPin,
  ShieldCheck,
  Sparkles,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import DynamicFieldWidget from './DynamicFieldWidget';

export default function ReviewPanel({
  documentId,
  fields = [],
  activeFieldId = null,
  onSelectEvidence,
  onUpdateField,
  onVerifyDocument,
}) {
  const [isVerifying, setIsVerifying] = useState(false);

  // Filter to failing/ungrounded/contested fields only
  const reviewFields = fields.filter(
    (f) =>
      f.status === 'needs_review' ||
      !f.evidence?.grounded ||
      (f.confidence || 0) < 0.85
  );

  const handleVerifyAll = async () => {
    setIsVerifying(true);
    try {
      if (onVerifyDocument) {
        await onVerifyDocument();
      }
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Banner */}
      <div className="p-4 rounded-xl border bg-amber-50/70 border-amber-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-600 text-white flex items-center justify-center shadow-sm">
            <AlertCircle size={20} />
          </div>
          <div>
            <h3 className="font-bold text-sm text-amber-950">Human-In-The-Loop Review Queue</h3>
            <p className="text-xs text-amber-800">
              Only failing, ungrounded, or contested fields are routed here for reviewer intervention.
            </p>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-primary btn-sm flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-semibold shadow-xs"
          onClick={handleVerifyAll}
          disabled={isVerifying}
        >
          <CheckCircle2 size={15} />
          <span>{isVerifying ? 'Verifying...' : 'Approve & Mark Verified'}</span>
        </button>
      </div>

      {reviewFields.length === 0 ? (
        <div className="p-10 text-center bg-white border border-emerald-200 rounded-xl shadow-xs">
          <CheckCircle2 size={44} className="mx-auto mb-3 text-emerald-500" />
          <h4 className="font-bold text-base text-slate-800">Zero Review Items Remaining</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            All extracted fields have passed evidence grounding, multi-pass reconciliation, and DSL constraints. This document is ready for automated approval.
          </p>
          <button
            type="button"
            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold"
            onClick={handleVerifyAll}
            disabled={isVerifying}
          >
            <Check size={14} /> Confirm Verification
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="font-bold text-xs uppercase tracking-wider text-slate-500">
              Items Requiring Confirmation ({reviewFields.length})
            </h4>
            <span className="text-xs text-slate-400">
              Click any field to jump to its source evidence on the document.
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {reviewFields.map((field) => (
              <DynamicFieldWidget
                key={field.id || field.key}
                field={field}
                isActive={activeFieldId === field.id || activeFieldId === field.key}
                onSelectEvidence={onSelectEvidence}
                onUpdateField={onUpdateField}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
