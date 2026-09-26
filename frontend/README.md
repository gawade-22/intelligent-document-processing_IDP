# IDP Frontend Console (React + Vite)

> Enterprise web application for the **Intelligent Document Processing (IDP)** platform. Provides document ingestion, processing queue visualization, side-by-side verification studio, candidate extraction reconciliation, and AI/LLM configuration.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features & Views](#-key-features--views)
- [Architecture & Design System](#-architecture--design-system)
- [Project Directory Structure](#-project-directory-structure)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Development Server](#development-server)
  - [Production Build](#production-build)
  - [Linting](#linting)
- [API Integration & Proxy Configuration](#-api-integration--proxy-configuration)
- [Key Components & Functionality](#-key-components--functionality)
- [Security Guidelines](#-security-guidelines)
- [Contributing](#-contributing)

---

## 🔍 Overview

The IDP Frontend is built with **React 19**, **Vite 8**, **React Router v7**, and **Lucide Icons**. It interfaces directly with the FastAPI backend to deliver a reactive, low-latency document processing console for operations teams, compliance validators, and system administrators.

### Core Capabilities:
- **Real-Time Monitoring**: Document processing throughput, status distributions, and extraction confidence metrics.
- **Verification Studio**: Two-panel view comparing raw OCR text against reconciled structured fields.
- **AI Extraction Studio**: Interactive management of LLM providers (Gemini), live connectivity diagnostics, and prompt template previews.
- **Human-in-the-Loop (HITL)**: Workflow queue for resolving extraction discrepancies and low-confidence edge cases.

---

## 🖥 Key Features & Views

### 1. Operations Dashboard (`/`)
- **Key Performance Indicators**: Total documents, auto-verified rate, pending review count, and average confidence gauge.
- **Live Search & Quick Filters**: Search by document name or ID; filter by status (`VERIFIED`, `NEEDS_REVIEW`, `PROCESSING`, `FAILED`).
- **Interactive Document Table**: Paginated table displaying file type badges, confidence score progress bars, timestamps, and contextual action menus (`View Details`, `Send to Review`).

### 2. Document Details & Extraction Studio (`/documents/:id`)
- **Dual-Pane Layout**:
  - **Left Pane (Extraction Breakdown)**: Reconciled key-value fields, confidence score per field, and source attribution badges (`[Rule]`, `[AI]`, `[Reconciled]`).
  - **Right Pane (Raw Content & OCR)**: Tabbed viewer displaying raw document text, OCR segments, and candidate JSON payloads.
- **On-Demand AI Extraction**: Trigger fresh LLM extraction (`rule_plus_llm`, `llm`, or `rule`) directly with real-time status updates.
- **Extraction Candidate Inspector (`ExtractionComparison.jsx`)**: Side-by-side comparison of deterministic rule extraction vs. LLM output with highlight on matching or conflicting fields.

### 3. AI / LLM Configuration Studio (`/ai-settings`)
- **Minimal, Professional UI**: Clean status cards showing engine health, active provider, model, and API key readiness.
- **Live Connectivity Diagnostics**: Single-click "Test Connection" button that validates API key validity and network latency against Google Gemini.
- **Prompt Template Editor**: Customize system instructions and document prompts with real-time variable interpolation previews (`{document_type}`, `{requested_fields}`, `{document_text}`).
- **Zero-Exposure Security**: API keys are securely persisted to backend `.env` and displayed only as masked tokens (`************`).

### 4. Human-in-the-Loop (HITL) Review Queue (`/review`)
- Filter and prioritize documents marked as `NEEDS_REVIEW` due to low confidence (<85%) or field discrepancy.
- Approve, override, or edit field values before marking documents as `VERIFIED`.

### 5. Document Ingestion Center (`/upload`)
- Drag-and-drop file upload supporting PDF, PNG, JPG, CSV, and Excel formats.
- Real-time upload progress and automated transition into the extraction pipeline.

---

## 🎨 Architecture & Design System

The application uses a pure CSS design system defined in `src/App.css` and `src/index.css`:

| Design Token | Value | Purpose |
| :--- | :--- | :--- |
| `--bg-main` | `#f8fafc` | Clean neutral application background |
| `--bg-card` | `#ffffff` | Elevated component surface |
| `--primary` | `#2563eb` | Primary enterprise brand blue |
| `--primary-hover`| `#1d4ed8` | Interactive state highlight |
| `--success` | `#16a34a` | High confidence / `VERIFIED` status |
| `--warning` | `#d97706` | Medium confidence / `NEEDS_REVIEW` status |
| `--danger` | `#dc2626` | Processing error / conflict state |
| `--border` | `#e2e8f0` | Subtle, accessible dividers |
| `--font-sans` | Inter, system-ui | Modern, legible typography |

---

## 📁 Project Directory Structure

```text
frontend/
├── index.html                   # HTML entrypoint
├── package.json                 # Dependencies & build scripts
├── vite.config.js               # Vite config & API reverse proxy
├── public/                      # Static brand assets
└── src/
    ├── main.jsx                 # Application bootstrapping & root React render
    ├── App.jsx                  # Main router, navigation layout & routing state
    ├── App.css                  # Comprehensive design system, themes & animations
    ├── index.css                # Base stylesheet and typography resets
    ├── api/                     # Modular HTTP API client services
    │   ├── client.js            # Base fetch wrapper with error handling
    │   ├── documents.js         # Document queries, uploads, stats, and actions
    │   └── ai.js                # AI config, test connection, prompt preview, re-extraction
    ├── components/              # Reusable UI component library
    │   ├── Header.jsx           # Global search bar, notifications, and user header
    │   ├── Sidebar.jsx          # Primary navigation menu
    │   ├── IdpLogo.jsx          # Vector IDP application logo
    │   ├── StatsCards.jsx       # Dashboard KPI metric cards
    │   ├── StatCard.jsx         # Individual KPI tile with trend indicators
    │   ├── DocumentTable.jsx    # Enterprise document data grid with actions
    │   ├── DocumentViewerModal.jsx # Quick document modal preview
    │   ├── StatusBadge.jsx      # Pill badge for VERIFIED, NEEDS_REVIEW, etc.
    │   ├── FilterDrawer.jsx     # Slide-out advanced query filter
    │   ├── UploadModal.jsx      # Modal upload dialog
    │   ├── UploadView.jsx       # Dedicated document drag-and-drop page
    │   ├── ReviewQueueView.jsx  # HITL review queue page
    │   ├── AnalyticsView.jsx    # Document throughput & performance analytics
    │   ├── AuditLogView.jsx     # System event & pipeline audit log
    │   └── ai/                  # AI / LLM Configuration & Verification Studio
    │       ├── AIStatusCard.jsx         # Engine status, active model, and health indicator
    │       ├── AIConfigCard.jsx         # Provider selector, model picker, and API key input
    │       ├── AIProviderSelector.jsx   # LLM provider dropdown (Gemini, etc.)
    │       ├── AIModelSelector.jsx      # Model picker (gemini-1.5-flash, gemini-2.5-pro, etc.)
    │       ├── APIKeyInput.jsx          # Secure masked key field with visibility toggle
    │       ├── AIConnectionTest.jsx     # Ping diagnostic component with latency report
    │       ├── PromptEditor.jsx         # Prompt template editor with dynamic token preview
    │       ├── DocumentDetailsView.jsx  # 2-pane extraction verification studio
    │       └── ExtractionComparison.jsx # Rule vs. LLM candidate reconciliation breakdown
    └── pages/
        └── AISettings.jsx       # Consolidated AI / LLM Configuration page
```

---

## 🚀 Getting Started

### Prerequisites
- **Node.js**: `v18.0.0` or higher
- **npm**: `v9.0.0` or higher
- Running IDP FastAPI Backend (`http://127.0.0.1:8000`)

### Installation

Navigate to the `frontend` folder and install dependencies:

```bash
cd frontend
npm install
```

### Development Server

Start the Vite development server with Hot Module Replacement (HMR):

```bash
npm run dev
```

The frontend will be accessible at:
```text
http://127.0.0.1:3000/
```

### Production Build

Create an optimized production bundle:

```bash
npm run build
```

To locally preview the production build:
```bash
npm run preview
```

### Linting

Run Oxlint to check code quality and detect potential issues:

```bash
npm run lint
```

---

## 🔌 API Integration & Proxy Configuration

In development, Vite proxies all `/api` requests to the local FastAPI backend to eliminate CORS issues:

```javascript
// vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

### Frontend API Client Modules:
- **`src/api/documents.js`**:
  - `fetchDocuments(params)`: Fetch filtered, paginated documents
  - `fetchDocument(id)`: Fetch individual document metadata & extracted content
  - `uploadDocument(file)`: Multipart upload for PDFs, images, spreadsheets
  - `fetchStats()`: Aggregate processing statistics
- **`src/api/ai.js`**:
  - `getAIConfig()`: Fetch provider, model, and masked key status
  - `updateAIConfig(payload)`: Save provider, model, API key, or prompt override
  - `testAIConnection()`: Trigger live connectivity check to LLM provider
  - `previewPrompt(documentType)`: Request compiled prompt preview
  - `getDocumentExtraction(id)`: Fetch rule vs. LLM candidate extraction data
  - `triggerAIExtraction(id, method)`: Run extraction with `rule_plus_llm`

---

## 🔒 Security Guidelines

1. **Zero Secret Storage**: Never store API keys or credentials in frontend code, Git commits, `localStorage`, or `sessionStorage`.
2. **Server-Side Validation**: All data inputs (prompts, model names, document parameters) are sanitized and validated by the backend Pydantic models.
3. **Safe Rendering**: All dynamic document text and OCR outputs are treated as untrusted strings and safely rendered without raw `dangerouslySetInnerHTML`.

---

## 🤝 Contributing

1. Check existing components in `src/components/` before creating new ones to maintain visual and stylistic consistency.
2. Verify that `npm run build` passes with zero errors before pushing changes.
3. Test all responsive breakpoints (Desktop 1440px, Laptop 1024px, Mobile 768px).
