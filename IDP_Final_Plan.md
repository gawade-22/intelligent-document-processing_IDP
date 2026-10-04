# Dynamic Intelligent Document Processing: Final Plan

Project: `gawade-22/intelligent-document-processing_IDP` (FastAPI + React + PostgreSQL)
Date: 4 Oct 2026
Inputs merged: (A) my first plan, (B) your attached 39-section plan, (C) my reading of the actual repo code.

---

## Part 1. Review of the attached plan

### 1.1 Overall verdict
The attached plan has the right core idea and is stronger than my first plan in several places. It should become the backbone. It also has gaps that would hurt in implementation. The final plan below keeps its architecture and fixes those gaps.

### 1.2 What to adopt (the plan is better than mine here)

| Idea in the attached plan | Why it is right |
|---|---|
| One universal pipeline, no per-type pipelines | This is the real fix for the root cause I found in the repo (13 hardcoded types, `general` falling back to invoice fields) |
| `UniversalDocument` as the contract between backend and frontend | Makes the UI and the exports independent of document type |
| Parser describes what physically exists; meaning is decided later | Clean separation of concerns |
| "Unknown" never stops extraction | Required for "we don't know what users will upload" |
| System confidence computed from evidence, never the LLM's self-reported number | Correct; self-reported LLM confidence is poorly calibrated |
| Candidate generation + reconciliation + `NEEDS_REVIEW` on conflict | Right idea (corrected in 1.3 below) |
| Extraction versioning (run id, model, prompt version, pipeline version) | Enables comparison, regression checks, and a strong demo |
| Provider abstractions for LLM, OCR and document processor | Your repo already has this for LLMs; extend it |
| Job queue with observable states | Needed once OCR + layout + LLM are involved |
| Spreadsheet intelligence (sheets, headers, types, stats) | CSV/Excel are first-class inputs, not text blobs |
| Strangler migration: keep the old pipeline running while the new one is built | Safest way to change a 40k-line system |
| Acceptance suite of 12 tests; "never add a document type by adding code" | Good, testable definition of done |

### 1.3 What to change (gaps and risks)

| # | Issue in the attached plan | Why it matters | Change made in the final plan |
|---|---|---|---|
| 1 | **Pure runtime discovery with no memory.** Field names are generated per document, so two resumes can come out as `full_name` vs `candidate_name` | Search, export, dashboards, comparisons and analytics need stable keys | Add a **Schema Registry**: discovered schemas are cached, reused for similar documents, and mapped to stable canonical keys. Templates live as *data*, never as code (Section 4.4) |
| 2 | "Candidates from parser, OCR, LLM, vision, rules" is conceptually muddled. A parser or OCR engine produces *text*, not a value for a field that was only discovered at runtime | The example (OCR says X, parser says X, LLM says Y) cannot occur for free-form fields | Redefine: candidates come from **independent extraction passes** (text-LLM, vision-LLM, optionally a second model). The parser/OCR text is used for **grounding** (is the value really in the source?) and **bbox location** (Section 4.6) |
| 3 | "Rules" as a candidate source and "relevant validation rules inferred" is vague; also contradicts the no-hardcoding goal if rules are per document type | Risk of rebuilding `InvoiceValidator` under a new name | Generic validators by data type (code) + **inferred cross-field rules expressed in a small safe DSL**, executed deterministically (not by the LLM) (Section 4.8) |
| 4 | The Insight Engine lists resume/bank/invoice insights by name | That is hardcoded per-type knowledge in disguise | Insights are **proposed by the LLM from the discovered schema** and **computed by generic aggregators** (sum, group-by, min/max, trend, date-range) over typed fields and tables (Section 4.10) |
| 5 | LLM asked to return `evidence location` (bbox) | LLMs cannot reliably give pixel/box coordinates | LLM returns a **verbatim quote + page**; your code **matches the quote to parsed blocks/words** to compute the bbox (Section 4.6) |
| 6 | Confidence formula is a list of signals with no weights | Arbitrary weights give false precision | Combine signals, then **calibrate on the labelled eval set** so 0.95 means about 95% correct (Section 4.9) |
| 7 | Evaluation framework is step 16 of 18 | Without measurement the early steps cannot be judged | **Evaluation moves to Phase 0** and gates every later phase |
| 8 | Async workers are step 15 | Docling + OCR + LLM make request-time processing impractical from the start | Job-state model and a worker are introduced in Phase 1 |
| 9 | 14+ relational tables (`document_blocks`, `document_table_cells`, ...) up front | Heavy migration before you know the shapes | **Hybrid storage:** store the `UniversalDocument` as JSONB per run, normalise only what you query (documents, runs, fields, corrections, audit). Split further later (Section 4.16) |
| 10 | Docling **and** PP-StructureV3 as co-primary, plus three optional cloud providers | Two heavy stacks (PaddlePaddle, possibly GPU) double the operational burden | **Benchmark in Phase 0**, pick one primary parser/OCR, keep the other as fallback, cloud providers optional and last |
| 11 | No mention of privacy / PII / retention / cost | Medical records and bank statements are in scope | Dedicated security & privacy section; cost and latency budgets (Section 4.17) |
| 12 | No handling of dynamic-schema limits of the LLM API | Claude's structured outputs limit optional/union parameters (24 and 16 per request) and ignore `pattern/min/max` | Extract **section by section**, validate constraints in your own code (Section 4.5) |
| 13 | No timeline, no exit criteria per phase | Hard to plan or demonstrate | Phased roadmap with measurable exit criteria (Part 5) |
| 14 | "Remove old code" (Phase 18) without a rule for when | Premature removal breaks the demo | Remove a legacy path only when the new path **beats it on the eval set** |

### 1.4 Statement on "no hardcoding"
The attached plan states this correctly: the goal is **no hardcoded document types, field names, templates, vendor layouts or extraction branches**. Generic code (data-type validators, normalisers, confidence maths, security) is expected and fine. The final plan follows this exact rule.

### 1.5 Statement on "100% accurate"
Not achievable on arbitrary documents with any library or model. The target is **measured high accuracy on auto-accepted fields**, with every value tied to evidence, and a human-review route for everything uncertain. Claims will be backed by numbers from the evaluation harness (Part 6).

---

## Part 2. Design principles (final)

1. **One universal pipeline.** No `if document_type == ...` in core code or in React.
2. **Understand, then discover, then extract.** The field list is an *output* of the system, not an input.
3. **Every value has evidence** (page, quote, box) and is **verified against the source text**.
4. **Never fabricate.** Unknown, low confidence or conflict becomes `NEEDS_REVIEW`.
5. **Stable keys on top of dynamic discovery** (Schema Registry), so data stays comparable over time.
6. **Knowledge is data, not code.** Templates, validation rules and insight definitions are stored records that can be edited without deployment.
7. **Everything replaceable** behind provider interfaces (LLM, OCR, parser, cloud Document AI).
8. **Measure first.** No change merges without the evaluation harness showing it does not regress.
9. **Strangler migration.** Old pipeline stays live until the new one wins.

---

## Part 3. Findings from the current repo that drive the plan

| Finding | Location |
|---|---|
| 13 types hardcoded in three places that already disagree | `document_classifier.py`, `extraction_prompt.py`, `ai_config.py` |
| Unknown documents become `general` with invoice fields | `document_classifier.py` |
| Keyword-scoring classifier | `document_classifier.py` |
| ~3,000-line invoice-only heuristic extractor, special-cased in the pipeline | `extraction.py`, `processing_pipeline.py` |
| Shallow rules for other types (16-item skill list; "Projects section present") | `multi_type_extractor.py` |
| Flat string values; no nested lists or tables | `extract_all` output |
| Text-only parsing with `pypdf`; LLM input truncated to 12,000 characters, no page images | `pdf_parser.py`, `ai_config.py` |
| Normalise/validate only for invoices | `processing_pipeline.py` |
| No evaluation set; confidence not calibrated | whole repo |
| Outdated model names in config (`gemini-1.5-*`, `claude-3-5-sonnet`) | `ai_config.py` |
| ~1,300 receipt PDFs inside the app repo | `archive/` |

Worth keeping: provider abstraction (`services/ai/`), HITL and audit, prompt-injection defence, tabular parser, JSON column `extracted_data`, the test suite.

*Scope: I read pipeline, classifier, extractors, prompts, OCR/PDF/tabular parsers, AI config, models and frontend entry points. I did not run the app, so there are no measured accuracy numbers yet.*

---

## Part 4. Final architecture

```
UPLOAD (PDF, PNG/JPG, CSV, XLSX, DOCX)
   │
   ▼
[1] Intake & validation ── hash, size/page limits, malware/format checks, dedupe cache
   │
   ▼
[2] Ingestion → UniversalDocument (physical structure only)
      per-page native/scanned routing · layout · reading order · tables · bboxes · OCR confidence
   │
   ▼
[3] Classification (open label + family + confidence; "unknown" continues)
   │
   ▼
[4] Schema resolution ── Schema Registry lookup ── match? reuse : discover (LLM) → canonicalise keys
   │
   ▼
[5] Extraction (text-LLM + vision-LLM passes, section by section, structured JSON, quote + page)
   │
   ▼
[6] Grounding & evidence ── find quote in parsed text → bbox; reject ungrounded values
   │
   ▼
[7] Reconciliation ── compare passes; agree → accept, conflict → flag
   │
   ▼
[8] Normalisation (by inferred data type + locale) & Validation (generic validators + DSL rules)
   │
   ▼
[9] Confidence (calibrated) & Routing ── VERIFIED / NEEDS_REVIEW (only failing fields)
   │
   ▼
[10] Insights (LLM-proposed definitions + deterministic aggregators)
   │
   ▼
[11] Output: dynamic JSON contract ──► React generic renderers ──► HITL ──► feedback to eval set
```

### 4.1 Universal contracts

**UniversalDocument** (stored as JSONB per processing run)

```json
{
  "document": {"id": "", "file_name": "", "format": "", "page_count": 0, "language": "", "hash": ""},
  "pages": [{"n": 1, "width": 0, "height": 0, "image_ref": "", "source": "native|ocr|mixed"}],
  "blocks": [{"id": "", "page": 1, "type": "heading|paragraph|list|kv|figure|footer", "text": "", "bbox": [0,0,0,0], "reading_order": 0, "ocr_conf": 0.0}],
  "tables": [{"id": "", "page": 1, "bbox": [], "headers": [], "rows": [], "ocr_conf": 0.0}],
  "sheets": [{"name": "", "columns": [], "dtypes": {}, "row_count": 0, "stats": {}}]
}
```

**Extraction result (the frontend contract)**

```json
{
  "document": {}, "classification": {"primary_type": "", "family": "", "confidence": 0.0, "alternatives": []},
  "schema": {"schema_id": "", "version": 1, "origin": "template|discovered", "sections": []},
  "fields": [{
    "id": "", "key": "stable_canonical_key", "label": "Human label", "section": "",
    "value": "", "normalized_value": "", "data_type": "string|number|date|money|percent|email|phone|id|text|bool",
    "confidence": 0.0,
    "evidence": {"page": 1, "quote": "", "bbox": [0,0,0,0], "grounded": true},
    "passes": [{"engine": "text-llm", "value": ""}, {"engine": "vision-llm", "value": ""}],
    "validation": {"status": "pass|warn|fail", "messages": []},
    "status": "verified|needs_review|edited", "editable": true
  }],
  "tables": [{"id": "", "key": "", "title": "", "headers": [], "rows": [], "confidence": 0.0, "source": {"page": 1, "bbox": []}}],
  "entities": [], "relationships": [], "summary": "",
  "insights": [{"id": "", "title": "", "kind": "metric|chart|flag|text", "definition": {}, "value": null}],
  "validation": {}, "review": {}, "run": {"run_id": "", "provider": "", "model": "", "prompt_version": "", "pipeline_version": ""}
}
```

Differences from the attached plan: `key` (stable) separated from `label` (display), `grounded` flag, `passes` for reconciliation, and `run` metadata.

### 4.2 Ingestion
- **Format routing:** digital PDF → layout parser; scanned PDF/PNG/JPG → page render + OCR/layout; DOCX → Docling/python-docx; CSV/XLSX → tabular profiler (existing parser plus header inference, multi-sheet and merged-cell handling).
- **Decide per page**, not per file (mixed PDFs).
- **Candidate stack (to be chosen by Phase 0 benchmark):**
  - Docling for digital PDFs/DOCX (structured document object; slower on CPU).
  - PaddleOCR with PP-StructureV3 for scans and tables (layout detection, OCR, table recognition, reading order).
  - Tesseract (already installed) as fallback.
  - PyMuPDF4LLM is light but has no OCR; Marker and MinerU are alternatives for complex layouts.
- **Licences:** check each before commercial use (PyMuPDF is AGPL; Surya weights carry a commercial threshold). Docling and PaddleOCR are permissive.
- Output is only physical structure. No field meaning is assigned here.

### 4.3 Classification
- LLM call on a compact view: first-page text, headings, table headers, small thumbnail for scans.
- Returns `primary_type` (open vocabulary), `family`, `confidence`, `alternatives`.
- Keep the old keyword classifier as a **cheap cross-check only**; disagreement lowers confidence.
- `unknown` proceeds to schema discovery. Multi-document files are split by page-range classification.

### 4.4 Schema Registry and Schema Discovery (the core)
1. **Fingerprint** the document (type label, family, header/section structure, table headers).
2. **Lookup** in the registry:
   - Match found → reuse the stored schema (consistent keys, cheaper).
   - No match → **discover**: LLM proposes sections, fields (name, data type, repeating or not), tables (name, columns), and suggested validation rules and insight definitions.
3. **Canonicalise keys:** map proposed names to existing canonical keys (for example `candidate_name` / `full_name` → `person.full_name`) using a small ontology plus embedding similarity, so equivalent fields share a key across documents.
4. **Store** the schema (versioned). Admin can edit, merge, rename or promote it.
5. **Seed templates:** today's 13 types are converted *once* into registry rows (data), replacing the three hardcoded lists. No code path knows them by name.

This satisfies "no hardcoded types" and also gives stable keys for search, export and analytics.

### 4.5 Extraction
- Input: UniversalDocument + schema. Never plain text only: structured text, sections, tables and page images where useful.
- **Section by section** (and page by page for long tables) instead of truncating at 12,000 characters. This also respects structured-output complexity limits (Claude: 24 optional and 16 union-typed parameters per request).
- **Tables:** take rows from the parsed table structure; the LLM only maps columns to schema fields. Long statements are processed page by page and concatenated.
- Use the provider's **structured-output / JSON-schema mode**; the schema is generated at runtime from the registry entry and cached. Constraints such as `pattern`, `minLength`, `minimum` are not supported there, so they are enforced by your own validators.
- Each field returns `value`, `data_type`, `quote` (verbatim), `page`.
- Prompts are generic: `classification`, `schema_discovery`, `extraction`, `reconciliation`, `insights`. Keep your existing "document text is untrusted" injection defence.
- Use a cheaper model first; escalate to a stronger model **only for fields that fail verification**.
- Refresh the model list in config to currently supported models (verify against provider docs).

### 4.6 Grounding and evidence
- **Grounding check:** fuzzy-match `quote` and `value` against parsed/OCR text. Not found → `grounded=false` → value rejected or sent to review. This is the main protection against hallucination.
- **Locate bbox:** map the matched text span to word/block boxes from the parser/OCR. The UI highlights it.
- Claude's native Citations feature cannot be combined with structured outputs, so evidence is produced as ordinary schema fields and verified by your code.

### 4.7 Reconciliation (corrected definition)
- Run two or more **independent passes**: text-LLM vs vision-LLM, and optionally a second model on contested fields.
- Compare normalised values per field:
  - All agree and grounded → accept.
  - Disagree → check which value is grounded in the source; if both or neither, `NEEDS_REVIEW`.
- Record all pass values in `passes` so the reviewer sees why a field was flagged.
- Deterministic regex candidates (generic by data type, such as email/date/amount patterns) may be added as an extra signal, but never as per-document-type branches.

### 4.8 Normalisation and validation
- **Normalisation by inferred data type + locale** (dates DD/MM vs MM/DD, ₹ and lakh-style commas, European decimals). Identifiers stay identifiers.
- **Generic validators:** string, number, date, email, phone, currency, percentage, list, table, evidence, cross-field.
- **Inferred cross-field rules** use a small safe DSL, executed by code (not by the LLM). Example, proposed during schema discovery and stored with the schema:

```json
{"rule": "sum_equals", "target": "total", "terms": ["tables.items.amount", "fields.tax"], "tolerance": 0.01}
{"rule": "running_balance", "table": "transactions", "opening": "opening_balance", "debit": "debit", "credit": "credit", "balance": "balance"}
{"rule": "date_order", "earlier": "issue_date", "later": "expiry_date"}
{"rule": "in_range", "value": "result", "min": "ref_min", "max": "ref_max", "severity": "warn"}
```

  The rule *vocabulary* (sum, running balance, date order, range, uniqueness, regex-by-type) is generic code; which rules apply to a document is data.
- Rules proposed by the LLM are validated for safety and syntax before being stored.

### 4.9 Confidence and routing
Signals per field: OCR quality, layout quality, grounding result, evidence match quality, pass agreement, data-type validity, DSL rule results, schema consistency.
- Combine into one score, then **calibrate on the labelled eval set** (reliability curve) so scores reflect real accuracy.
- Never use the LLM's self-reported confidence as the final value.
- Routing: auto-verify only when grounded + agreed + valid + above a configurable threshold; otherwise `NEEDS_REVIEW` with **only the failing fields** shown.

### 4.10 Insights
- Two layers:
  1. **Generic, always on:** summary, key entities, important dates, important numbers, detected sections and tables, flags from failed validation rules.
  2. **Schema-driven:** insight definitions proposed at schema discovery and stored with the schema, such as `{"kind":"metric","agg":"sum","table":"transactions","column":"credit"}`, `{"kind":"chart","type":"line","x":"date","y":"balance"}`, `{"kind":"flag","rule":"in_range"}`.
- The numbers are computed by generic aggregators (sum, avg, min/max, count, group-by, trend, date span) over typed tables, so results are exact and not LLM arithmetic. The LLM only writes the narrative summary from computed facts.

### 4.11 Spreadsheets and CSV
Profile workbook → sheets → tables → headers → data types → missing values → duplicates → basic statistics. Then the same schema discovery produces fields, tables and insights (for example "Employee Dataset: 1,245 rows, 9 departments, missing salary records, average salary") with no predefined Excel schema. Formulas are not executed (existing safe behaviour kept).

### 4.12 Dynamic React UI
- Generic renderers only: `DocumentHeader`, `DynamicSections`, `DynamicFields`, `DynamicTables`, `DynamicLists`, `DynamicInsights`, `EvidenceViewer`, `ValidationPanel`, `ReviewPanel`.
- Generic field widgets chosen by `data_type`: Text, Number, Date, Currency, Boolean, Array, Object, Table, LongText.
- Layout: left = document viewer with evidence highlight (click a field → jump and box the source); right = sections from the schema, each field showing confidence, status, validation messages, edit-in-place.
- Schema editor: add/remove/rename a field and **re-extract** (run versioning keeps history).
- Single upload screen ("Upload Document"), no per-type pages.
- Suggested libraries: `react-pdf` (viewer + overlays), `@tanstack/react-table`, Recharts, optionally JSON Forms/RJSF for editing.
- Acceptance: a newly discovered field (for example `project_budget`) appears with **zero frontend changes**.

### 4.13 Human-in-the-loop
Review shows only failing fields with evidence and all pass values. After a correction: normalise → validate → recompute confidence → mark `edited`/`verified`. Every correction writes an audit record and is added to the eval/few-shot pool.

### 4.14 Async processing and failure recovery
- Queue + workers (Celery/RQ/Arq) with states: `UPLOADED, QUEUED, ANALYZING, UNDERSTANDING, CLASSIFYING, SCHEMA_DISCOVERY, EXTRACTING, GROUNDING, VALIDATING, GENERATING_INSIGHTS, NEEDS_REVIEW, COMPLETED, FAILED`, each timed and observable.
- Fallback chains: primary parser fails → fallback parser; primary OCR fails or is poor → Tesseract; poor OCR → vision model; LLM timeout → retry with backoff; LLM unavailable → degraded mode (parsed structure + generic detectors + review); uncertainty → HITL. The system never silently emits a low-quality value.
- Idempotent retries, per-page parallelism, hash cache (same file → same result unless reprocessed).

### 4.15 Providers
Interfaces: `LLMProvider`, `OCRProvider`, `DocumentProcessorProvider`.
- LLM: keep Gemini and OpenAI-compatible; add Anthropic; optional local model.
- OCR: Paddle, Tesseract.
- Document processor: Local (Docling/Paddle). Optional adapters for Google Document AI, Azure Document Intelligence, AWS Textract, used for benchmarking, verification or fallback, never as a hard dependency.

### 4.16 API and data model
**API (v2, alongside v1)**
```
POST   /api/v2/documents/upload
GET    /api/v2/documents
GET    /api/v2/documents/{id}
GET    /api/v2/documents/{id}/status
GET    /api/v2/documents/{id}/structure
GET    /api/v2/documents/{id}/extraction
GET    /api/v2/documents/{id}/evidence
GET    /api/v2/documents/{id}/insights
PATCH  /api/v2/documents/{id}/fields/{field_id}
POST   /api/v2/documents/{id}/verify
POST   /api/v2/documents/{id}/reprocess
GET    /api/v2/schemas            (registry: list, view, edit, promote)
POST   /api/v2/documents/{id}/ask (optional, document Q&A later)
```

**Tables (hybrid: JSONB for flexible content, relational for what you query)**
- `documents`, `extraction_runs` (run metadata + `universal_document` JSONB + `result` JSONB)
- `document_schemas` (versioned, origin, status), `schema_aliases` (canonical key mapping)
- `extracted_fields` (run_id, key, value, confidence, status, evidence JSONB)
- `review_corrections`, `audit_logs`, `eval_cases`
- Split blocks/cells into their own tables later only if queries demand it.

### 4.17 Security, privacy and operations
- PII/PHI: decide cloud-LLM vs private deployment up front; encryption at rest; retention and deletion policy; redaction in logs (existing sanitiser extended); access control per document.
- Prompt-injection defence kept; schema and DSL outputs from the LLM are validated before use.
- Limits: file size, page count, timeouts; password-protected files return a clear status (existing).
- Cost and latency budgets per page; cost tracking per run; model escalation only on failures.
- Observability: stage timings, failure reasons, per-field accuracy dashboards, drift alerts.

### 4.18 Backend and frontend layout
```
backend/app/
  api/routes/ (v1, v2)   core/   models/   schemas/
  services/ ingestion/ understanding/ classification/ schema_registry/ extraction/
            grounding/ reconciliation/ normalization/ validation/ confidence/ insights/ review/
  providers/ llm/ ocr/ document_ai/
  prompts/ classification.py schema_discovery.py extraction.py reconciliation.py insights.py
  workers/ document_worker.py
frontend/src/
  components/ upload/ document-viewer/ dynamic-fields/ dynamic-tables/ dynamic-sections/
              insights/ evidence/ validation/ review/
  pages/ Dashboard Upload DocumentDetail Review Settings
  services/api  hooks  utils  types
```

---

## Part 5. Migration and roadmap

### 5.1 What happens to current code

| Current component | Action |
|---|---|
| `services/ai/` provider layer, HITL, audit, dashboards, security helpers, tabular parser | **Keep** (refactor into `providers/`) |
| `pdf_parser.py`, `ocr_engine.py` | **Wrap** behind the ingestion interface; keep as fallbacks |
| `document_classifier.py` | **Demote** to cross-check, then delete after the new classifier wins |
| `extraction_prompt.py` configs, `DOCUMENT_TYPES`, `SUPPORTED_DOCUMENT_TYPES` | **Convert to registry seed data**, then delete |
| `InvoiceExtractor` (~3k lines), `multi_type_extractor` regex | **Keep behind a flag as a cross-check** during migration; **delete** when the new path beats it on the eval set |
| `InvoiceValidator`, `InvoiceNormalizer` | **Replace** with generic validators/normaliser; keep logic as test oracles |
| Old frontend per-type rendering | **Replace** with generic renderers |
| `archive/` | **Move out** of the app repo (object storage or data repo) |

Branch `dynamic-idp-rebuild`; new endpoints under `/api/v2`; old `/api` unchanged until cut-over.

### 5.2 Roadmap (one to two engineers; estimates are rough)

| Phase | Weeks | Work | Exit criteria |
|---|---|---|---|
| **0. Foundations** | 1–2 | Branch + baseline. Build golden set (30–50 docs per major family incl. scans, photos, multilingual, unknown PDFs, CSV, XLSX) with ground truth. Eval harness + CI gate. Benchmark parsers/OCR on your documents. Refresh dependencies and model list. Move `archive/`. | Baseline report for the current system; chosen primary parser/OCR stack |
| **1. Universal model + async skeleton** | 2 | `UniversalDocument`, extraction contract, JSONB run storage, job queue, state machine, `/api/v2` skeleton | Any supported file produces a stored UniversalDocument via the queue |
| **2. Ingestion** | 2 | Per-page native/OCR routing, tables, bboxes, DOCX, spreadsheet profiler, fallback chains | Table fidelity and text recall measured on the golden set |
| **3. Classification + Schema Registry + extraction** | 3 | Open-label classifier, registry with canonical keys, discovery, seed data from current 13 types, sectioned structured extraction, vision pass | Resume, bank statement, medical report, certificate **and an unseen type** extract into correct nested structures; no invoice fallback |
| **4. Grounding, reconciliation, validation, confidence** | 3 | Grounding + bbox, two-pass reconciliation, generic validators + DSL, calibrated confidence, field-level routing | Hallucination rate (ungrounded values) near zero; auto-accept precision target met |
| **5. Dynamic UI + insights** | 3 (overlaps 4) | Generic renderers, evidence viewer, tables, insights engine, schema editor + re-extract, review UI | New document type renders with **zero frontend changes** |
| **6. Hardening + cut-over** | 2 | Privacy controls, cost tracking, observability, load tests, run comparison view, remove legacy paths that lost on the eval set, optional cloud Document AI adapters | All 12 acceptance tests pass; legacy code removed |

Total about 14–16 weeks.

---

## Part 6. Evaluation and acceptance

**Golden set:** invoices, resumes, bank statements, medical reports, certificates, academic documents, technical reports, unknown PDFs, scanned PDFs, phone photos, CSV, multi-sheet Excel. Public datasets can help bootstrap (CORD and SROIE for receipts, FUNSD for forms, DocILE for business documents); your `archive/` receipts can be input documents but need ground-truth labels.

**Metrics:** classification accuracy; field precision, recall, F1; exact match; numeric and date accuracy; table cell accuracy and row recall; evidence localisation accuracy; **ungrounded-value rate**; auto-accept precision; human-review rate; calibration error of confidence; processing time; cost per page; failure rate.

**Acceptance tests (all must pass):**
1. Invoice A → correct dynamic fields.
2. Invoice B, different layout → same semantic information with no template code.
3. Resume → name, education, skills, experience, projects.
4. Bank statement → account information + transaction table.
5. Medical report → patient/report/test structure.
6. Certificate → recipient, issuer, credential, dates.
7. Previously unseen PDF → unknown/novel type, extraction still occurs.
8. Scanned PDF → OCR + layout + extraction.
9. Photo of a document → preprocessing + OCR/vision.
10. CSV → schema inference + structured table.
11. Multi-sheet Excel → workbook understanding.
12. Bad-quality document → low confidence + review, no fabricated values.
13. (Added) Same document processed twice → same canonical keys; two documents of the same type → shared canonical keys.
14. (Added) Dropping a new document type needs no code change in backend or frontend.

**Demo script:** upload invoice → resume → bank statement → a completely new document type; show schema discovered, evidence highlight, validation flags, insights, and a run-comparison between two pipeline versions.

---

## Part 7. Risks

| Risk | Mitigation |
|---|---|
| Hallucinated values | Mandatory quote + grounding check; reject ungrounded values |
| Inconsistent field names across documents | Schema Registry + canonical key mapping |
| Cost and latency on long documents | Section chunking, cheap-model-first with escalation, caching, async workers |
| Poor scans/photos | Preprocessing, OCR confidence, vision pass, review route |
| Two heavy parsing stacks | Benchmark early, one primary, one fallback |
| Sensitive data leaving your environment | Decide hosting early; local parsers; LLM provider choice or self-hosting |
| Licence surprises | Review licences before shipping commercially |
| Regressions during migration | Eval gate in CI; strangler approach; remove legacy only after it loses |
| LLM-proposed rules/insights being wrong or unsafe | Validate DSL syntax and bounds; admin review for promoted schemas |

---

## Part 8. Decisions needed from you
1. May document content go to a cloud LLM, or must medical/bank documents stay on your own infrastructure?
2. Expected volume and latency: seconds or minutes per document?
3. Languages: English only, or also Hindi/Marathi and others (affects OCR and locale handling)?
4. LLM provider: keep Gemini, add Claude, or both behind the provider interface?
5. Is a GPU available for PaddleOCR/Docling, or CPU only? (affects the Phase 0 stack choice)
6. Target auto-accept precision and who handles review?
7. Can you share 20–30 real or anonymised sample documents across your priority types for Phase 0?

---

## Sources
- [Claude structured outputs documentation](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Best open-source PDF-to-Markdown tools 2026](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026)
- [Python OCR library comparison for invoices](https://invoicedataextraction.com/blog/python-ocr-library-comparison-invoices)
- Repo: https://github.com/gawade-22/intelligent-document-processing_IDP
- Your attached plan (reviewed in Part 1)
