# 010 — Source Pages Redesign: PDF Preview, Unified Review & Search

**Status:** Draft (v2 — simplified approach)  
**Author:** WorkbenchIQ Engineering  
**Date:** 2026-02-23  
**Updated:** 2026-02-23  
**Scope:** Frontend-only — reuses existing `PDFViewer` pattern and file-serving endpoint

---

## 1. Problem Statement

The current Source Pages view has three usability gaps:

| Gap | Current State | Impact |
|-----|---------------|--------|
| **No PDF preview** | Users see only extracted markdown text. To verify extraction quality they must switch to the Documents tab, download/open the PDF, and manually find the right page. | Slow QA loop; errors in extraction go unnoticed |
| **Disconnected layout** | Batch Summaries and Source Pages are placed side-by-side with no explicit linkage. Users can't easily see which summary corresponds to which raw text or which PDF page. | Cognitive overhead; hard to audit AI work |
| **No search** | There is no way to search across extracted text or batch summaries. In a 60-page APS, finding "cholesterol" requires scrolling through every page. | Wasted time; important findings get missed |

### Design Principles

1. **One screen, three lenses** — PDF original → extracted text → AI summary should be visible simultaneously for any page range.
2. **Search-first** — a global search bar at the top that highlights hits across all three columns.
3. **Zero data contract changes** — no new fields on `ApplicationMetadata`, no new backend endpoints, no new dependencies.
4. **Reuse existing infrastructure** — leverage the `claims/PDFViewer` component pattern and the existing `GET /api/applications/{id}/files/{filename}` endpoint already used by the mortgage persona.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                  Source Review View (full width)                   │
├─────────┬──────────────────────┬─────────────────────────────────┤
│         │                      │                                 │
│  Page   │   PDF Preview        │   Extracted Markdown Text       │
│  Nav    │   (browser-native    │   + Batch Summary Card          │
│  +      │    <object> embed)   │                                 │
│ Search  │                      │   ← from existing               │
│         │   ← from existing    │      markdown_pages data        │
│         │     file endpoint    │                                 │
└─────────┴──────────────────────┴─────────────────────────────────┘
```

### Data Flow (PDF preview — no new backend work)

```
Browser                              FastAPI Backend
   │                                      │
   │  <object data=                       │
   │    getMediaUrl("/api/applications/   │
   │    {id}/files/{filename}")           │
   │    + "#page={N}">                    │
   │  ──────────────────────────────────► │
   │                                      │
   │                 1. load_file() from   │
   │                    local or blob     │
   │                 2. Return with        │
   │                    Content-Type:      │
   │                    application/pdf   │
   │  ◄──────────────────────────────────│
   │                                      │
   │  Browser renders PDF inline via      │
   │  built-in PDF viewer; #page=N        │
   │  navigates to the correct page       │
```

**Key insight:** The existing endpoint at `GET /api/applications/{app_id}/files/{filename}` already serves PDFs with correct `Content-Type` and range-request headers. The existing `claims/PDFViewer` component already renders PDFs inline using `<object>` with `<embed>` fallback. We simply adapt this pattern for inline (non-modal) use and add `#page=N` URL fragments for page-level navigation.

---

## 3. Backend Changes

### None.

The existing infrastructure is sufficient:

| Existing Asset | How It's Used |
|----------------|---------------|
| `GET /api/applications/{app_id}/files/{filename}` (api_server.py L677) | Serves PDF files from local or blob storage with proper Content-Type, Accept-Ranges, Content-Disposition headers |
| `load_file()` (app/storage.py) | Abstracts local filesystem vs Azure Blob Storage — endpoint already uses this |
| `getMediaUrl()` (frontend/src/lib/api.ts) | Constructs direct URL to backend bypassing Next.js proxy — used by existing `PDFViewer` |

### Unchanged Data Contracts

| Contract | Change? |
|----------|---------|
| `ApplicationMetadata` | No change |
| `MarkdownPage` | No change |
| `BatchSummary` | No change |
| `StoredFile` | No change |
| `GET /api/applications/{id}` | No change |
| `GET /api/applications/{id}/files/{filename}` | No change (already exists) |
| `requirements.txt` / `pyproject.toml` | No change (no new dependencies) |

### Azure Blob / Container Compatibility

This approach works identically in local development and Azure container deployment because:
- The file endpoint already uses the storage abstraction layer (`load_file`)
- No disk caching is needed — the browser caches the PDF after first load
- No server-side rendering libraries (PyMuPDF) needed
- `#page=N` navigation is handled entirely by the browser's built-in PDF viewer

---

## 4. Frontend Design

### 4.1 New Component: `SourceReviewView`

Replaces the current `case 'source'` branch in `WorkbenchView.tsx`. This is a single full-width component that composes three columns.

#### Layout (Three-Column + Header)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 Search across pages and summaries...          [Filters ▼] [Copy]  │
│  ─────────────────────────────────────────────────────────────────────  │
│  "cholesterol" — 4 matches: Page 3, Page 7, Page 12, Batch 2          │
├─────────┬───────────────────────┬───────────────────────────────────────┤
│         │                       │                                       │
│  PAGE   │   PDF ORIGINAL        │   EXTRACTED TEXT                      │
│  NAV    │                       │                                       │
│         │   ┌───────────────┐   │   ┌─────────────────────────────┐    │
│  ┌───┐  │   │               │   │   │ ## Patient: John Smith     │    │
│  │ 1 │  │   │  (Rendered    │   │   │                             │    │
│  ├───┤  │   │   PDF page    │   │   │ Date of Birth: 1965-03-12  │    │
│  │ 2 │  │   │   as PNG)     │   │   │   ...                       │    │
│  ├───┤  │   │               │   │   │ Cholesterol: 242 mg/dL     │    │
│  │ 3 │◄─│   │               │   │   │   ^^^^^^^^^ highlighted     │    │
│  ├───┤  │   └───────────────┘   │   └─────────────────────────────┘    │
│  │ 4 │  │                       │                                       │
│  ├───┤  │   Zoom: [–] 100% [+]  │   ┌─────────────────────────────┐    │
│  │ 5 │  │                       │   │ 📋 BATCH SUMMARY (Batch 1)  │    │
│  ├───┤  │                       │   │ Pages 1-5                    │    │
│  │...│  │                       │   │                               │    │
│  │   │  │                       │   │ Key findings from this       │    │
│  │   │  │                       │   │ section of the document...   │    │
│  └───┘  │                       │   └─────────────────────────────┘    │
│         │                       │                                       │
│ FILE A  │  ← Prev   3/47  Next →│   [Copy Page] [Copy All Visible]    │
│ FILE B  │                       │                                       │
└─────────┴───────────────────────┴───────────────────────────────────────┘
```

#### Column Widths

| Column | Width | Resizable | Content |
|--------|-------|-----------|---------|
| Page Navigator | `w-44` (176px) | No | Page list grouped by file, with search match indicators |
| PDF Preview | `flex-1` (~40%) | Yes (drag handle) | Rendered PDF page image with zoom controls |
| Extracted Text | `flex-1` (~40%) | Yes | Markdown text + contextual batch summary card |

### 4.2 Wireframe Detail: Page Navigator (Left Column)

```
┌────────────────────┐
│ 📄 medical-records │  ← File group header (collapsed/expanded)
│   ┌──────────────┐ │
│   │ ● Page 1     │ │  ● = has search match
│   │   Page 2     │ │
│   │ ● Page 3  ◄──│─│── selected (highlighted bg)
│   │   Page 4     │ │
│   │ ● Page 5     │ │
│   └──────────────┘ │
│                     │
│ 📄 lab-results     │  ← Second file
│   ┌──────────────┐ │
│   │ ● Page 6     │ │
│   │   Page 7     │ │
│   └──────────────┘ │
│                     │
│ ─────────────────── │
│ BATCH SUMMARIES     │  ← Batch navigation section
│   Batch 1 (1-5)  ● │
│   Batch 2 (6-10)   │
│   Batch 3 (11-15)  │
└────────────────────┘
```

**Behavior:**
- Click a page → center column shows that page's PDF image, right column shows that page's extracted markdown
- Click a batch → right column scrolls to that batch summary, center shows first page of that batch
- Search match dots (●) appear next to pages/batches that contain search hits
- Current selection is highlighted with persona primary color

### 4.3 Wireframe Detail: PDF Preview (Center Column)

```
┌────────────────────────────────────┐
│  ┌──────────────────────────────┐  │
│  │ [–] 100% [+]   [↗ New Tab]  │  │  ← Toolbar: zoom + open in tab
│  └──────────────────────────────┘  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │                              │  │
│  │  Browser-native PDF viewer   │  │
│  │  via <object> / <embed>      │  │
│  │                              │  │
│  │  URL:                        │  │
│  │  getMediaUrl("/api/          │  │
│  │    applications/{id}/files/  │  │
│  │    {filename}") + "#page=3"  │  │
│  │                              │  │
│  │  (includes built-in scroll,  │  │
│  │   search, and zoom)          │  │
│  │                              │  │
│  └──────────────────────────────┘  │
│                                    │
│  ← Prev    Page 3 / 47    Next →  │  ← Pagination (syncs all columns)
└────────────────────────────────────┘
```

**Behavior:**
- Uses `<object>` with `<embed>` fallback (same pattern as existing `claims/PDFViewer`)
- URL constructed via `getMediaUrl()` pointing to existing file endpoint + `#page=N` fragment
- Browser's built-in PDF viewer renders the page — includes native scroll, text search, and zoom
- Custom zoom controls apply CSS `transform: scale()` on the container (same as existing `PDFViewer`)
- Prev/Next buttons update the `#page=N` fragment and sync all three columns
- Error fallback shows "Open Full PDF" link to view in new tab (same pattern as existing `PDFViewer`)
- **No image prefetching needed** — browser caches the entire PDF after first load; page navigation via `#page=N` is instant
- When page navigates to a new file (multi-file applications), the `<object>` src changes to the new file URL

### 4.4 Wireframe Detail: Extracted Text + Batch Summary (Right Column)

```
┌─────────────────────────────────────────┐
│  📄 Page 3 — medical-records.pdf        │  ← Page label
│  ─────────────────────────────────────  │
│                                         │
│  ## Examination Notes                   │  ← Extracted markdown rendered  
│                                         │     as prose (not <pre> block)
│  The patient presented with elevated    │
│  **cholesterol** levels of 242 mg/dL.   │  ← Search hits highlighted
│  Blood pressure was recorded at         │     with yellow background
│  138/88 mmHg on two separate visits.    │
│                                         │
│  HbA1c: 6.8% (pre-diabetic range)      │
│  ...                                    │
│                                         │
│  ─────────────────────────────────────  │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ 🤖 AI Summary — Batch 1        │    │  ← Contextual batch card
│  │    (Pages 1 – 5)                │    │     Only shows the batch that  
│  │                                 │    │     covers the current page
│  │  Key Findings:                  │    │
│  │  • Elevated cholesterol (242)   │    │
│  │  • Pre-diabetic HbA1c (6.8%)   │    │
│  │  • Hypertension Stage 1        │    │
│  │                                 │    │
│  │  [Expand Full Summary]          │    │
│  └─────────────────────────────────┘    │
│                                         │
│  [Copy Page Text]                       │
└─────────────────────────────────────────┘
```

**Behavior:**
- Extracted markdown rendered with proper formatting (headings, bold, lists) instead of the current raw `<pre>` block
- Search terms highlighted with `<mark>` tags (yellow bg)
- Batch summary card appears **contextually** — shows only the batch that contains the current page
- Card is collapsible; "Expand Full Summary" reveals the full batch summary text
- If no batch summaries exist (standard processing mode), just show the extracted text

### 4.5 Wireframe Detail: Search Bar (Top)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 Search pages and summaries...                    [✕]   3 / 12     │
│  ─────────────────────────────────────────────────────────────────────  │
│  Matches: Page 3 • Page 7 • Page 12 • Batch 1 • Batch 3              │
│           ^^^^^^                                                       │
│           clickable chips — click to jump to that page/batch           │
└─────────────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Debounced search (300ms) across `markdown_pages[].markdown` and `batch_summaries[].summary`
- Results shown as clickable chips below the search bar
- `3 / 12` shows current match index / total matches
- Up/Down arrow keys or `Enter` to cycle through matches
- `Esc` clears search
- Case-insensitive, simple substring matching (no need for fuzzy/regex)
- Page navigator dots (●) update in real-time as user types

### 4.6 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` / `→` | Previous / next page |
| `Ctrl+F` or `/` | Focus search bar |
| `Enter` | Next search match |
| `Shift+Enter` | Previous search match |
| `Esc` | Clear search / blur search |
| `+` / `-` | Zoom in / out on PDF preview |

---

## 5. Component Breakdown

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| `SourceReviewView` | `frontend/src/components/SourceReviewView.tsx` | Top-level orchestrator. Manages selected page, search state, and column layout |
| `InlinePdfViewer` | `frontend/src/components/InlinePdfViewer.tsx` | Center column — inline PDF viewer using `<object>`/`<embed>` (adapted from `claims/PDFViewer` for non-modal use), zoom controls, page navigation via `#page=N` |
| `ExtractedTextPane` | `frontend/src/components/ExtractedTextPane.tsx` | Right column — renders markdown with search highlighting + contextual batch card |
| `PageNavigator` | `frontend/src/components/PageNavigator.tsx` | Left sidebar — page list grouped by file with search indicators |
| `SearchBar` | `frontend/src/components/SearchBar.tsx` | Top search bar with match chips and navigation |

### Reused Components

| Component | File | How Reused |
|-----------|------|------------|
| `claims/PDFViewer` | `frontend/src/components/claims/PDFViewer.tsx` | **Pattern reference** — `InlinePdfViewer` adapts its `<object>`/`<embed>` approach, `getMediaUrl()` URL construction, zoom controls, and error fallback. The original remains unchanged and continues serving the mortgage workbench as a modal. |

### Modified Components

| Component | Change |
|-----------|--------|
| `WorkbenchView.tsx` | Replace source view code with `<SourceReviewView>` |
| `SourcePagesPanel.tsx` | Not modified — kept for potential reuse elsewhere, but no longer used in main workbench source view |
| `BatchSummariesPanel.tsx` | Not modified — kept for standalone use, but batch summaries are now integrated into `ExtractedTextPane` |

### No Changes

| Component | Why |
|-----------|-----|
| `lib/types.ts` | No new types needed; existing `MarkdownPage` and `BatchSummary` are sufficient |
| `lib/api.ts` | The page image URL is a simple `<img src>` URL — no API client function needed (just compose the URL string) |

---

## 6. Search Implementation Detail

All client-side. No backend search API needed.

```typescript
interface SearchResult {
  type: 'page' | 'batch';
  pageNumber?: number;       // for page matches
  batchNum?: number;         // for batch matches
  matchCount: number;        // occurrences in this page/batch
  snippets: string[];        // short context strings around each match
}

function searchSourceContent(
  query: string,
  pages: MarkdownPage[],
  batchSummaries: BatchSummary[]
): SearchResult[] {
  if (!query || query.length < 2) return [];
  const q = query.toLowerCase();
  const results: SearchResult[] = [];
  
  // Search pages
  for (const page of pages) {
    const text = page.markdown.toLowerCase();
    const matches = countOccurrences(text, q);
    if (matches > 0) {
      results.push({
        type: 'page',
        pageNumber: page.page_number,
        matchCount: matches,
        snippets: extractSnippets(page.markdown, query, 2), // max 2 snippets
      });
    }
  }
  
  // Search batch summaries
  for (const batch of batchSummaries) {
    const text = batch.summary.toLowerCase();
    const matches = countOccurrences(text, q);
    if (matches > 0) {
      results.push({
        type: 'batch',
        batchNum: batch.batch_num,
        matchCount: matches,
        snippets: extractSnippets(batch.summary, query, 2),
      });
    }
  }
  
  return results;
}
```

### Text Highlighting

In `ExtractedTextPane`, the markdown text is split and reassembled with `<mark>` wrappers:

```tsx
function highlightText(text: string, query: string): React.ReactNode[] {
  if (!query) return [text];
  const parts = text.split(new RegExp(`(${escapeRegex(query)})`, 'gi'));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase()
      ? <mark key={i} className="bg-yellow-200 rounded px-0.5">{part}</mark>
      : part
  );
}
```

---

## 7. PDF Loading Strategy

### URL Construction

```typescript
// For a given MarkdownPage, construct the PDF URL with page fragment
const pdfUrl = getMediaUrl(`/api/applications/${appId}/files/${page.file}`);
const pdfUrlWithPage = `${pdfUrl}#page=${page.page_number}`;
```

- `getMediaUrl()` (from `lib/api.ts`) constructs a direct URL to the FastAPI backend, bypassing the Next.js proxy so the browser receives proper `Content-Type` and `Accept-Ranges` headers
- The `#page=N` fragment tells the browser's built-in PDF viewer to scroll to page N
- For multi-file applications, each file group in the page navigator points to a different PDF URL; changing files reloads the `<object>` with the new file's URL

### Browser Caching

No custom caching needed. The browser caches the full PDF after the first `<object>` load. Navigating between pages via `#page=N` is instant since the PDF is already in memory. Switching between files triggers a new download, but the browser's HTTP cache handles subsequent views.

### Skeleton Loading

While the PDF loads for the first time, show:
```
┌──────────────────────────────┐
│                              │
│    ┌──────────────────┐      │
│    │  ░░░░░░░░░░░░░░  │      │
│    │  ░░░ Loading ░░░  │      │
│    │  ░░░  PDF  ░░░░  │      │
│    │  ░░░░░░░░░░░░░░  │      │
│    └──────────────────┘      │
│                              │
└──────────────────────────────┘
```

### Error State

If the `<object>` tag fails to load (same pattern as existing `PDFViewer`):
```
┌──────────────────────────────┐
│                              │
│    ⚠️ PDF preview            │
│    unavailable for           │
│    this page                 │
│                              │
│    [Open Full PDF]           │
│                              │
└──────────────────────────────┘
```

The "Open Full PDF" link opens the original uploaded file in a new tab via `getMediaUrl()`.

### Multi-File Handling

`MarkdownPage.file` identifies which PDF a page came from. When the user navigates from a page in file A to a page in file B, the `InlinePdfViewer` detects the file change and reloads the `<object>` with the new file URL. Within the same file, only the `#page=N` fragment changes (instant navigation).

---

## 8. Responsive Behavior

| Viewport | Layout |
|----------|--------|
| **Desktop (≥1280px)** | Full 3-column layout as diagrammed |
| **Tablet (768-1279px)** | 2-column: page nav collapses into a dropdown; PDF preview + extracted text side by side |
| **Mobile (<768px)** | Single column with tab switcher: [PDF] [Text] [Summary] |

The primary use case is desktop (underwriter workstation), so tablet/mobile are graceful fallbacks, not primary targets.

---

## 9. Implementation Plan

### Phase 1: Core Frontend Components (4 tasks)

| Task | Description | Effort |
|------|-------------|--------|
| T1 | Create `PageNavigator` — file-grouped page list with selection state, batch summary section | S |
| T2 | Create `InlinePdfViewer` — `<object>`/`<embed>` PDF viewer adapted from `claims/PDFViewer` for inline use, zoom controls, `#page=N` navigation, error fallback | M |
| T3 | Create `ExtractedTextPane` — rendered markdown with contextual batch summary card, copy button | M |
| T4 | Create `SourceReviewView` — orchestrator combining PageNavigator + InlinePdfViewer + ExtractedTextPane, manage selected page state and column layout | M |

### Phase 2: Search (2 tasks)

| Task | Description | Effort |
|------|-------------|--------|
| T5 | Create `SearchBar` — debounced input, match chips, match counter, keyboard nav | M |
| T6 | Wire search into all three columns — highlight text in ExtractedTextPane, update page nav dots, filter logic | M |

### Phase 3: Integration & Polish (1 task)

| Task | Description | Effort |
|------|-------------|--------|
| T7 | Replace `case 'source'` in WorkbenchView with `<SourceReviewView>`, keyboard shortcuts, test with multi-file and large docs (50+ pages) | S |

**Total: 7 tasks — est. 1-2 days (frontend-only, no backend deployment needed)**

---

## 10. File Changes Summary

| File | Action | Scope |
|------|--------|-------|
| `frontend/src/components/SourceReviewView.tsx` | **New** — main orchestrator (~250 lines) | Frontend |
| `frontend/src/components/InlinePdfViewer.tsx` | **New** — inline PDF viewer adapted from claims/PDFViewer (~100 lines) | Frontend |
| `frontend/src/components/ExtractedTextPane.tsx` | **New** — text + batch summary (~150 lines) | Frontend |
| `frontend/src/components/PageNavigator.tsx` | **New** — sidebar nav (~100 lines) | Frontend |
| `frontend/src/components/SearchBar.tsx` | **New** — search with highlighting (~100 lines) | Frontend |
| `frontend/src/components/WorkbenchView.tsx` | **Modify** — swap source view branch (~10 lines changed) | Frontend |
| `frontend/src/components/SourcePagesPanel.tsx` | **Unchanged** — kept for backward compat | — |
| `frontend/src/components/BatchSummariesPanel.tsx` | **Unchanged** — kept for standalone use | — |
| `frontend/src/components/claims/PDFViewer.tsx` | **Unchanged** — continues serving mortgage workbench | — |
| `frontend/src/lib/types.ts` | **Unchanged** | — |
| `frontend/src/lib/api.ts` | **Unchanged** | — |
| `api_server.py` | **Unchanged** | — |
| `requirements.txt` / `pyproject.toml` | **Unchanged** | — |

---

## 11. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Should we support text selection syncing between PDF preview and extracted text? | **No** — complex OCR coordinate mapping; defer to future |
| 2 | Should the PDF preview support annotations or drawing? | **No** — read-only viewer |
| 3 | ~~Should we render PDF pages client-side with pdf.js instead of server-rendered PNGs?~~ | **Resolved** — use browser-native `<object>` embed (same as existing `claims/PDFViewer`). No new dependencies, no server-side rendering, works with blob storage. |
| 4 | ~~Maximum DPI for the rendered image?~~ | **Resolved** — not applicable; browser renders PDF natively at screen resolution |
| 5 | Should `#page=N` navigation work reliably across all browsers? | **Yes** — `#page=N` is supported by Chrome, Edge, and Firefox built-in PDF viewers. Safari uses Preview which may not support it; fallback is manual scroll. Underwriter workstations are predominantly Chrome/Edge. |
| 6 | Should we support side-by-side view of two different pages? | **No** — single page focus is sufficient for QA workflow; defer if requested |

---

## 12. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-23 | Use browser-native PDF rendering (`<object>` embed) instead of server-side PyMuPDF | Least disruptive: no new backend endpoint, no new Python dependency, no Azure container caching concerns. Mortgage persona already uses this pattern via `claims/PDFViewer`. |
| 2026-02-23 | Adapt existing `claims/PDFViewer` pattern for inline use rather than importing it directly | The existing component is modal-only (fixed overlay). An inline variant shares the same `<object>`/`<embed>` approach and `getMediaUrl()` URL construction but renders within the layout flow. |
| 2026-02-23 | Frontend-only scope — zero backend changes | Existing `GET /api/applications/{id}/files/{filename}` endpoint already serves PDFs with correct headers from both local and blob storage. |
