# Spec 011: Body System Deep Dive — Enhanced Patient Summary

**Feature Branch**: `011-body-system-deep-dive`  
**Created**: 2026-02-27  
**Status**: Draft  
**Input**: Pilot user feedback requesting body-system-categorized medical summaries with page references, pending investigations, last office visit, abnormal labs, vitals, and family history — presented through an interactive human body diagram similar to the automotive claims DamageViewer pattern.

---

## Problem Statement

Pilot underwriters reviewed 6+ APS cases and reported:

1. **Material omissions** — The current `customer_profile` summary prompt generates a single paragraph that misses important details (e.g., pending investigations, specialist referrals, imaging orders).
2. **Chronological Overview is not intuitive** — While accurate, the timeline format doesn't map to how underwriters think (by body system, not by date).
3. **No quick source navigation** — Underwriters must manually search the PDF after finding something in the summary. They want **clickable page references** on every finding.
4. **Missing key sections** — The current summary lacks: pending investigations, last office visit (LOV), body-system-categorized diagnoses/treatments, abnormal lab results (chronological), latest vitals, and structured family history.

### What Underwriters Actually Want

A structured summary organized the way they write their own manual summaries:

```
Pending Investigations → LOV & Last Labs → Body Systems (GU, MSK, GI, ENT, …) → Abnormal Labs → Vitals → Family History
```

Each entry should include a **clickable page reference** that jumps to the source page in the PDF viewer.

---

## Overview

This specification defines:

1. **Body System Deep Dive Modal** — A full-screen modal opened via a "Deep Dive" button on `PatientSummary`, containing:
   - An **interactive human body diagram** (SVG, front-facing anatomical silhouette) with clickable body regions
   - **Body system cards** with diagnoses, treatments, consults, and imaging — each with page references
   - **Pending investigations**, **Last Office Visit**, **Abnormal Labs**, **Latest Vitals**, and **Family History** sections
2. **New LLM Prompts** — Additional prompts in the `medical_summary` section to extract body-system-categorized data with page references
3. **Backend API Enhancement** — New endpoint or extended analysis to produce structured body-system data
4. **Source Page Navigation** — Clickable page numbers that open `SourcePagesPanel` at the referenced page

---

## User Stories

### US-1: Deep Dive Button on Patient Summary (Priority: P0)
> As an underwriter, I want a "Deep Dive" button on the Patient Summary card that opens a comprehensive body-system-categorized medical summary, so I can quickly review all clinical findings organized the way I think about risk.

**Acceptance Scenarios**:
1. **Given** an application with completed analysis, **When** I click "Deep Dive" on the Patient Summary, **Then** a full-screen modal opens showing the body system deep dive view.
2. **Given** analysis has not been run, **When** I click "Deep Dive", **Then** the modal opens with a prompt to run analysis first.
3. **Given** the deep dive modal is open, **When** I press Escape or click outside, **Then** the modal closes.

### US-2: Interactive Body Diagram (Priority: P0)
> As an underwriter, I want to see a human body silhouette with highlighted regions indicating which body systems have findings, so I can visually identify areas of concern at a glance.

**Acceptance Scenarios**:
1. **Given** the deep dive modal is open, **When** body system data is loaded, **Then** an SVG body diagram highlights regions with findings (e.g., head/ENT, chest/cardiovascular, abdomen/GI, joints/MSK).
2. **Given** a body region has findings, **When** I click on it, **Then** the detail panel scrolls to and highlights that body system's section.
3. **Given** a body region has no findings, **Then** it appears in a neutral/dimmed state and is not clickable.
4. **Given** multiple severity levels exist, **Then** regions are color-coded (e.g., red = high concern, amber = moderate, green = monitored/stable).

### US-3: Body System Detail Cards (Priority: P0)
> As an underwriter, I want each body system section to show diagnoses, treatments, consults, and imaging in reverse chronological order with page references, so I can review clinical details efficiently.

**Acceptance Scenarios**:
1. **Given** a body system (e.g., MSK) has findings, **When** I view its section, **Then** I see:
   - Diagnosis name and date diagnosed (latest first)
   - Treatments for each diagnosis (latest first)
   - Consults and specialist visits (latest first)
   - Imaging related to the diagnosis (latest first)
2. **Given** each finding has a source page, **When** displayed, **Then** a clickable page badge (e.g., `p.8`) appears next to the entry.
3. **Given** I click a page reference, **Then** the app navigates to the Source Pages view at that specific page.

### US-4: Pending Investigations Section (Priority: P0)
> As an underwriter, I want to see all pending investigations (tests, referrals, consults, imaging) prominently at the top of the deep dive, so I know what clinical information is still outstanding.

**Acceptance Scenarios**:
1. **Given** the APS mentions pending tests or referrals, **When** the deep dive is shown, **Then** a "Pending Investigations" section appears at the top with each pending item, its date, description, and page reference.
2. **Given** no pending investigations exist, **Then** the section shows "No pending investigations identified."

### US-5: Last Office Visit Section (Priority: P0)
> As an underwriter, I want to see the last office visit date and a summary of what was discussed/planned, so I have the most recent clinical snapshot.

**Acceptance Scenarios**:
1. **Given** the APS contains visit records, **When** deep dive is shown, **Then** a "Last Office Visit" section shows the date, summary, and follow-up plans with page references.
2. **Given** lab work was done at the last visit, **Then** a brief lab summary is included with reference to the labs section.

### US-6: Abnormal Labs & Latest Vitals (Priority: P1)
> As an underwriter, I want abnormal lab results in chronological order and the latest vitals displayed clearly, so I can assess current health status.

**Acceptance Scenarios**:
1. **Given** the APS contains lab results, **When** deep dive is shown, **Then** an "Abnormal Lab Results" section lists only abnormal values in reverse chronological order with test name, value, date, and page reference.
2. **Given** vitals are recorded, **When** deep dive is shown, **Then** a "Latest Vitals" section shows the most recent BP, HR, weight, BMI, etc.

### US-7: Family History in Deep Dive (Priority: P1)
> As an underwriter, I want structured family history within the deep dive modal, listing each relative's conditions, so I can assess hereditary risk factors.

**Acceptance Scenarios**:
1. **Given** family history is documented, **When** deep dive is shown, **Then** a "Family History" section lists relatives, their conditions, and ages at diagnosis with page references.

### US-8: Page Reference Navigation (Priority: P0)
> As an underwriter, I want to click any page reference in the deep dive and be taken directly to that page in the source document viewer, so I can verify findings without manual searching.

**Acceptance Scenarios**:
1. **Given** I click a page reference badge (e.g., `p.8`), **When** the source pages view loads, **Then** the PDF viewer scrolls to page 8 with the view set to the `source` tab.
2. **Given** the deep dive modal is open, **When** I click a page reference, **Then** the modal closes and the source view opens at that page.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                            │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │ PatientSummary.tsx (existing)                                              │   │
│  │  + [Deep Dive] button → opens BodySystemDeepDiveModal                     │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                              │                                                   │
│                              ▼                                                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │ BodySystemDeepDiveModal.tsx (NEW)                                          │   │
│  │                                                                            │   │
│  │  ┌─────────────────────┬──────────────────────────────────────────────┐   │   │
│  │  │  BodyDiagram.tsx    │  Detail Panel (scrollable)                    │   │   │
│  │  │  (SVG silhouette)   │                                              │   │   │
│  │  │                     │  ┌──────────────────────────────────────┐    │   │   │
│  │  │  [Head/ENT]  ●      │  │ 🔴 Pending Investigations            │    │   │   │
│  │  │  [Chest/CV]  ●      │  │   - Unsatisfactory PAP... (p.8)     │    │   │   │
│  │  │  [Abdomen/GI] ●     │  ├──────────────────────────────────────┤    │   │   │
│  │  │  [GU]        ●      │  │ 📋 Last Office Visit                 │    │   │   │
│  │  │  [MSK]       ●      │  │   2025 Jul — mammogram pending...    │    │   │   │
│  │  │  [Skin]             │  ├──────────────────────────────────────┤    │   │   │
│  │  │  [Endo]             │  │ 🫁 ENT (Ear/Nose/Throat)            │    │   │   │
│  │  │                     │  │   Tinnitus dx May 2023...  (p.12)    │    │   │   │
│  │  │  Legend:             │  ├──────────────────────────────────────┤    │   │   │
│  │  │  🔴 High concern    │  │ 🦴 MSK (Musculoskeletal)            │    │   │   │
│  │  │  🟠 Moderate        │  │   OA dx 2019, bilateral knee...     │    │   │   │
│  │  │  🟢 Stable          │  ├──────────────────────────────────────┤    │   │   │
│  │  │  ⚪ No findings     │  │ 🔬 Abnormal Lab Results              │    │   │   │
│  │  │                     │  ├──────────────────────────────────────┤    │   │   │
│  │  │                     │  │ 💓 Latest Vitals                     │    │   │   │
│  │  │                     │  ├──────────────────────────────────────┤    │   │   │
│  │  │                     │  │ 👨‍👩‍👧‍👦 Family History                   │    │   │   │
│  │  │                     │  └──────────────────────────────────────┘    │   │   │
│  │  └─────────────────────┴──────────────────────────────────────────────┘   │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Components (NEW):                                                               │
│  ├── BodySystemDeepDiveModal.tsx  — Full-screen modal container                  │
│  ├── BodyDiagram.tsx              — SVG human silhouette with clickable regions   │
│  ├── BodySystemCard.tsx           — Card for each body system's findings          │
│  ├── PendingInvestigationsCard.tsx — Highlighted pending items section            │
│  ├── LastOfficeVisitCard.tsx       — LOV summary section                         │
│  ├── AbnormalLabsCard.tsx          — Chronological abnormal labs                 │
│  ├── LatestVitalsCard.tsx          — Most recent vitals snapshot                 │
│  └── PageRefBadge.tsx              — Clickable page number badge component       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ REST API
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                                    │
│                                                                                  │
│  Extended Analysis:                                                              │
│  ├── POST /api/applications/{id}/analyze  (existing — now runs deep dive too)    │
│                                                                                  │
│  New Prompt Sections (added to medical_summary):                                 │
│  ├── medical_summary.body_system_review      — Full body system extraction       │
│  ├── medical_summary.pending_investigations  — Pending tests/referrals           │
│  ├── medical_summary.last_office_visit       — LOV date and summary              │
│  ├── medical_summary.abnormal_labs           — Chronological abnormal labs        │
│  └── medical_summary.latest_vitals           — Most recent vitals snapshot       │
│                                                                                  │
│  Modified Modules:                                                               │
│  ├── app/personas.py              — New subsection definitions + types           │
│  ├── app/processing.py            — Orchestrate new prompts                      │
│  └── app/prompts.py               — Load new prompt templates                    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  prompts/prompts.json  (EXTENDED — new subsections added)                        │
│  app/personas.py       (EXTENDED — new prompt defaults + body system types)       │
│  frontend/src/lib/types.ts  (EXTENDED — new TypeScript interfaces)               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
│  Extracted   │────▶│  New LLM Prompts │────▶│  Structured JSON      │────▶│  Deep Dive Modal │
│  Markdown    │     │  (5 new sections)│     │  (body_system_review, │     │  (BodyDiagram +  │
│  (per page)  │     │                  │     │   pending_inv, LOV,   │     │   detail cards)  │
└──────────────┘     └──────────────────┘     │   abnormal_labs,      │     └──────────────────┘
                                               │   latest_vitals)     │
                                               └───────────────────────┘
```

---

## Data Structures

### 1. Body System Review (LLM Output Schema)

The core new data structure returned by the `body_system_review` prompt:

```json
{
  "body_systems": [
    {
      "system_code": "MSK",
      "system_name": "Musculoskeletal",
      "body_region": "joints_spine",
      "severity": "moderate",
      "diagnoses": [
        {
          "name": "Osteoarthritis, bilateral knees",
          "date_diagnosed": "2019",
          "status": "active",
          "page_references": [14, 22],
          "treatments": [
            {
              "description": "Cortisone injections",
              "date": "2020-03",
              "page_references": [15]
            },
            {
              "description": "Kinesiotherapy follow-up",
              "date": "2021-06",
              "page_references": [18]
            }
          ],
          "consults": [
            {
              "specialist": "Orthopedics",
              "date": "2019-11",
              "summary": "Initial assessment, bilateral knee OA confirmed",
              "page_references": [14]
            }
          ],
          "imaging": [
            {
              "type": "X-ray spine and sacrum",
              "date": "2025-01",
              "result": "No significant interval progression of DD changes and lower lumbar and lumbosacral arthropathy",
              "page_references": [8]
            },
            {
              "type": "X-ray hip",
              "date": "2022",
              "result": "Mild hip OA",
              "page_references": [19]
            }
          ]
        }
      ]
    }
  ]
}
```

### 2. Pending Investigations

```json
{
  "pending_investigations": [
    {
      "date": "2025-01",
      "description": "Unsatisfactory PAP in Sep 2024 — repeated today, red circle on cervix, ask Gynecologist for opinion",
      "type": "referral",
      "urgency": "high",
      "page_references": [8]
    }
  ]
}
```

### 3. Last Office Visit

```json
{
  "last_office_visit": {
    "date": "2025-07",
    "summary": "Mammogram pending Aug 2025, routine bloodwork due. Repeat colonoscopy 2028. F/u physical in Sep 2025 to review mammogram and progression on Saxenda.",
    "follow_up_plans": [
      "Mammogram — Aug 2025",
      "Follow-up physical — Sep 2025",
      "Repeat colonoscopy — 2028"
    ],
    "page_references": [3, 4]
  },
  "last_labs": {
    "date": "2024-08",
    "summary": "Essentially normal",
    "page_references": [12]
  }
}
```

### 4. Abnormal Lab Results

```json
{
  "abnormal_labs": [
    {
      "date": "2024-08-15",
      "test_name": "LDL Cholesterol",
      "value": "165",
      "unit": "mg/dL",
      "reference_range": "< 130 mg/dL",
      "interpretation": "Elevated",
      "page_references": [12]
    }
  ]
}
```

### 5. Latest Vitals

```json
{
  "latest_vitals": {
    "date": "2025-01",
    "blood_pressure": { "systolic": 128, "diastolic": 82 },
    "heart_rate": 72,
    "weight": { "value": 160, "unit": "lbs" },
    "height": { "value": "5'4\"", "unit": "ft/in" },
    "bmi": 27.4,
    "temperature": null,
    "respiratory_rate": null,
    "page_references": [7]
  }
}
```

### 6. Body Region Mapping (Diagram ↔ System Codes)

Maps body system codes to SVG regions for the interactive diagram:

```typescript
const BODY_REGION_MAP: Record<string, BodyRegionConfig> = {
  // Head & Neck
  "NEURO":   { region: "head",         label: "Neurological",      y: 8  },
  "ENT":     { region: "head",         label: "Ear/Nose/Throat",   y: 12 },
  "EYES":    { region: "head",         label: "Ophthalmology",     y: 10 },
  "DENTAL":  { region: "head",         label: "Dental",            y: 14 },

  // Chest
  "CV":      { region: "chest",        label: "Cardiovascular",    y: 28 },
  "RESP":    { region: "chest",        label: "Respiratory",       y: 32 },
  "BREAST":  { region: "chest",        label: "Breast",            y: 34 },

  // Abdomen
  "GI":      { region: "abdomen",      label: "Gastrointestinal",  y: 42 },
  "HEPATIC": { region: "abdomen",      label: "Hepatic/Liver",     y: 44 },
  "RENAL":   { region: "abdomen",      label: "Renal/Kidney",      y: 46 },

  // Pelvis
  "GU":      { region: "pelvis",       label: "Genitourinary",     y: 52 },
  "REPRO":   { region: "pelvis",       label: "Reproductive",      y: 54 },

  // Extremities
  "MSK":     { region: "joints_spine", label: "Musculoskeletal",   y: 60 },
  "VASC":    { region: "extremities",  label: "Vascular/Peripheral", y: 65 },

  // Systemic / Whole Body
  "ENDO":    { region: "systemic",     label: "Endocrine",         y: 38 },
  "HEME":    { region: "systemic",     label: "Hematology",        y: 40 },
  "DERM":    { region: "skin",         label: "Dermatology",       y: 70 },
  "PSYCH":   { region: "systemic",     label: "Psychiatric",       y: 6  },
  "IMMUNE":  { region: "systemic",     label: "Immunology",        y: 36 },
  "BUILD":   { region: "systemic",     label: "Build/Weight",      y: 48 },
};
```

---

## TypeScript Interfaces (frontend/src/lib/types.ts additions)

```typescript
// ============================================================================
// Body System Deep Dive Types
// ============================================================================

export interface PageReference {
  page: number;
  file?: string;  // For multi-file applications
}

export interface BodySystemTreatment {
  description: string;
  date: string;
  page_references: number[];
}

export interface BodySystemConsult {
  specialist: string;
  date: string;
  summary: string;
  page_references: number[];
}

export interface BodySystemImaging {
  type: string;
  date: string;
  result: string;
  page_references: number[];
}

export interface BodySystemDiagnosis {
  name: string;
  date_diagnosed: string;
  status: 'active' | 'resolved' | 'monitoring' | 'unknown';
  page_references: number[];
  treatments: BodySystemTreatment[];
  consults: BodySystemConsult[];
  imaging: BodySystemImaging[];
}

export interface BodySystem {
  system_code: string;
  system_name: string;
  body_region: string;
  severity: 'high' | 'moderate' | 'low' | 'normal';
  diagnoses: BodySystemDiagnosis[];
}

export interface PendingInvestigation {
  date: string;
  description: string;
  type: 'test' | 'referral' | 'consult' | 'imaging' | 'procedure';
  urgency: 'high' | 'medium' | 'low';
  page_references: number[];
}

export interface LastOfficeVisit {
  date: string;
  summary: string;
  follow_up_plans: string[];
  page_references: number[];
}

export interface LastLabs {
  date: string;
  summary: string;
  page_references: number[];
}

export interface AbnormalLab {
  date: string;
  test_name: string;
  value: string;
  unit: string;
  reference_range: string;
  interpretation: string;
  page_references: number[];
}

export interface LatestVitals {
  date: string;
  blood_pressure?: { systolic: number; diastolic: number };
  heart_rate?: number;
  weight?: { value: number; unit: string };
  height?: { value: string; unit: string };
  bmi?: number;
  temperature?: number | null;
  respiratory_rate?: number | null;
  oxygen_saturation?: number | null;
  page_references: number[];
}

export interface FamilyHistoryEntry {
  relative: string;
  condition: string;
  age_at_diagnosis?: string;
  outcome?: string;
  page_references: number[];
}

export interface BodySystemDeepDive {
  body_systems: BodySystem[];
  pending_investigations: PendingInvestigation[];
  last_office_visit: LastOfficeVisit | null;
  last_labs: LastLabs | null;
  abnormal_labs: AbnormalLab[];
  latest_vitals: LatestVitals | null;
  family_history: FamilyHistoryEntry[];
}
```

---

## LLM Prompt Design

### Design Principles

1. **One prompt per deep-dive section** — Keeps each prompt focused and the JSON schema small (reduces hallucination)
2. **Page references are mandatory** — Every finding must cite source page numbers from the document markdown (which includes page markers like `<!-- Page 8 -->`)
3. **Reverse chronological order** — Latest findings first, matching underwriter workflow
4. **Standardized terminology** — Reuse existing language/measurement standardization instructions from `prompts.json`
5. **Body system codes** — Use standard codes (MSK, CV, GI, GU, ENT, etc.) so the frontend can map to diagram regions

### New Prompt Sections

Five new subsections are added under `medical_summary` in `prompts.json` and `UNDERWRITING_DEFAULT_PROMPTS`:

#### 1. `medical_summary.body_system_review`

```
You are an expert medical underwriting assistant. Analyze the following medical records and extract all clinical findings organized by body system.

For EACH body system that has any findings in the records, create an entry with:

**Body System Codes** (use these exact codes):
- NEURO (Neurological), ENT (Ear/Nose/Throat), EYES (Ophthalmology)
- CV (Cardiovascular), RESP (Respiratory), BREAST (Breast)
- GI (Gastrointestinal), HEPATIC (Hepatic/Liver), RENAL (Renal/Kidney)
- GU (Genitourinary), REPRO (Reproductive)
- MSK (Musculoskeletal), VASC (Vascular/Peripheral)
- ENDO (Endocrine), HEME (Hematology), DERM (Dermatology)
- PSYCH (Psychiatric), IMMUNE (Immunology), BUILD (Build/Weight)

For each body system found, extract:
1. **Diagnoses** — Each diagnosis with date diagnosed, current status (active/resolved/monitoring), and page reference(s)
2. **Treatments** — For each diagnosis, list treatments in reverse chronological order with date and page reference(s)
3. **Consults** — Specialist visits related to this system, with date, specialist type, summary, and page reference(s)
4. **Imaging** — Any imaging studies (X-ray, MRI, CT, ultrasound, etc.) with date, type, result, and page reference(s)

**Severity Classification:**
- "high" — Active, uncontrolled, or newly diagnosed conditions requiring immediate underwriting attention
- "moderate" — Stable conditions under treatment, or conditions with pending workup
- "low" — Resolved conditions, or well-controlled chronic conditions
- "normal" — Screening/preventive findings with normal results

**Page References:** 
The document contains page markers like <!-- Page 1 -->, <!-- Page 2 -->, etc. For EVERY finding, include the page number(s) where the information was found. This is CRITICAL for underwriter verification.

**Ordering:** Within each body system, list diagnoses with the most recent first. Within each diagnosis, list treatments, consults, and imaging with the most recent first.

**Only include body systems that have actual findings in the records.** Do not create empty body systems.

IMPORTANT: Translate all non-English text to English. Convert metric units: kg → lbs, cm → feet/inches, °C → °F, mmol/L → mg/dL.

Return a JSON object with this exact schema:
{
  "body_systems": [
    {
      "system_code": "string (e.g., MSK)",
      "system_name": "string (e.g., Musculoskeletal)",
      "body_region": "string (e.g., joints_spine)",
      "severity": "high | moderate | low | normal",
      "diagnoses": [
        {
          "name": "string",
          "date_diagnosed": "string (YYYY-MM or YYYY)",
          "status": "active | resolved | monitoring | unknown",
          "page_references": [number],
          "treatments": [
            {
              "description": "string",
              "date": "string (YYYY-MM or YYYY)",
              "page_references": [number]
            }
          ],
          "consults": [
            {
              "specialist": "string",
              "date": "string",
              "summary": "string",
              "page_references": [number]
            }
          ],
          "imaging": [
            {
              "type": "string",
              "date": "string",
              "result": "string",
              "page_references": [number]
            }
          ]
        }
      ]
    }
  ]
}
```

#### 2. `medical_summary.pending_investigations`

```
You are an expert medical underwriting assistant. Analyze the following medical records and extract ALL pending investigations — any tests, referrals, consults, imaging, procedures, or follow-ups that have been ordered, recommended, or scheduled but not yet completed or with results still outstanding.

This is CRITICAL information for underwriters as pending investigations may reveal undiagnosed conditions that affect risk assessment.

Look for indicators such as:
- "pending", "scheduled", "ordered", "referred to", "follow-up", "repeat in", "due"
- Future appointment dates
- Tests ordered but results not yet documented
- Specialist referrals without documented visit
- Recommended procedures not yet performed

For each pending investigation, provide:
- **date**: When it was ordered/mentioned
- **description**: Full description including context (what triggered it, what it's investigating)
- **type**: One of: test, referral, consult, imaging, procedure
- **urgency**: high (potential malignancy, acute symptoms), medium (routine follow-up), low (preventive/screening)
- **page_references**: Source page number(s) — REQUIRED

IMPORTANT: Translate all non-English text to English.

Return a JSON object:
{
  "pending_investigations": [
    {
      "date": "string (YYYY-MM)",
      "description": "string",
      "type": "test | referral | consult | imaging | procedure",
      "urgency": "high | medium | low",
      "page_references": [number]
    }
  ],
  "summary": "string — brief one-sentence overview of all pending items"
}
```

#### 3. `medical_summary.last_office_visit`

```
You are an expert medical underwriting assistant. Analyze the following medical records and identify the MOST RECENT office/clinic visit and the MOST RECENT lab work.

**Last Office Visit (LOV):**
Find the latest documented physician/provider visit and extract:
- Date of visit
- Summary of what was discussed, examined, and any decisions made
- Follow-up plans and future appointments
- Page reference(s)

**Last Labs:**
Find the most recent set of lab work and extract:
- Date labs were drawn
- Overall summary (normal, abnormal findings if any)
- Page reference(s)

IMPORTANT: Translate all non-English text to English. Convert metric units: kg → lbs, cm → feet/inches, °C → °F, mmol/L → mg/dL.

Return a JSON object:
{
  "last_office_visit": {
    "date": "string (YYYY-MM or YYYY-MM-DD)",
    "summary": "string — comprehensive summary of the visit",
    "follow_up_plans": ["string — each planned follow-up item"],
    "page_references": [number]
  },
  "last_labs": {
    "date": "string (YYYY-MM or YYYY-MM-DD)",
    "summary": "string — overall lab assessment",
    "page_references": [number]
  }
}
```

#### 4. `medical_summary.abnormal_labs`

```
You are an expert medical underwriting assistant. Analyze the following medical records and extract ALL abnormal laboratory results.

For each abnormal lab result, provide:
- **date**: Date the lab was drawn/reported
- **test_name**: Standard name of the test (e.g., "LDL Cholesterol", "HbA1c", "TSH")
- **value**: The measured value
- **unit**: Unit of measurement (use US standard: mg/dL, mIU/L, etc.)
- **reference_range**: Normal reference range
- **interpretation**: Brief clinical interpretation (e.g., "Elevated", "Low", "Borderline high")
- **page_references**: Source page number(s) — REQUIRED

**Ordering:** List results in reverse chronological order (most recent first).

**Only include abnormal results.** Do not list normal lab values.

IMPORTANT: Convert metric units to US standard: mmol/L → mg/dL for glucose/lipids, μmol/L → mg/dL for creatinine/bilirubin, SI units → conventional units.

Return a JSON object:
{
  "abnormal_labs": [
    {
      "date": "string (YYYY-MM-DD or YYYY-MM)",
      "test_name": "string",
      "value": "string",
      "unit": "string",
      "reference_range": "string",
      "interpretation": "string",
      "page_references": [number]
    }
  ]
}
```

#### 5. `medical_summary.latest_vitals`

```
You are an expert medical underwriting assistant. Analyze the following medical records and extract the MOST RECENT set of vital signs recorded.

Look for:
- Blood pressure (systolic/diastolic in mmHg)
- Heart rate / Pulse (bpm)
- Weight (convert to lbs if in kg)
- Height (convert to feet/inches if in cm)
- BMI (calculated or recorded)
- Temperature (convert to °F if in °C)
- Respiratory rate (breaths per minute)
- Oxygen saturation (SpO2 %)

If a vital sign is not documented in the records, set it to null.

IMPORTANT: Convert metric units: kg → lbs, cm → feet/inches, °C → °F.

Return a JSON object:
{
  "latest_vitals": {
    "date": "string (YYYY-MM-DD or YYYY-MM)",
    "blood_pressure": { "systolic": number, "diastolic": number } | null,
    "heart_rate": number | null,
    "weight": { "value": number, "unit": "lbs" } | null,
    "height": { "value": "string", "unit": "ft/in" } | null,
    "bmi": number | null,
    "temperature": number | null,
    "respiratory_rate": number | null,
    "oxygen_saturation": number | null,
    "page_references": [number]
  }
}
```

---

## Frontend Components

### 1. BodySystemDeepDiveModal.tsx

**Layout**: Full-screen modal (similar to `PolicyReportModal`), split into two panels:

| Left Panel (30%) | Right Panel (70%) |
|---|---|
| Sticky body diagram | Scrollable detail sections |
| SVG human silhouette | Pending Investigations |
| Clickable body regions | Last Office Visit & Labs |
| Color-coded severity | Body System Cards (one per system) |
| Legend | Abnormal Lab Results |
| | Latest Vitals |
| | Family History |

**Behavior**:
- Opens via "Deep Dive" button on `PatientSummary`
- Deep dive data is populated automatically when `/analyze` runs — no separate trigger needed
- If analysis hasn't been run yet, shows a message prompting the user to run analysis first
- If analysis was run before this feature existed (legacy data), shows a "Re-run Analysis" button to regenerate with deep dive prompts included
- Close via Escape key, X button, or clicking backdrop

### 2. BodyDiagram.tsx

**Implementation**: SVG front-facing human silhouette (inspired by the `VehicleDiagram` pattern from `DamageViewer.tsx`).

```
         Head ●
          |
     Neck/Throat
      /       \
  L.Arm     R.Arm
      \       /
       Chest ●
         |
      Abdomen ●
         |
       Pelvis ●
      /       \
   L.Leg     R.Leg
      \       /
       Feet
```

**Regions** are SVG `<path>` elements with these interactive behaviors:
- **Highlighted** (colored fill) when the body system has findings
- **Clickable** — scrolls the right panel to the corresponding body system card
- **Tooltip on hover** — shows system name and severity
- **Color coding**:
  - Red fill (opacity 0.3) = high severity
  - Amber fill (opacity 0.3) = moderate severity
  - Green fill (opacity 0.2) = low/normal severity
  - Gray fill (opacity 0.1) = no findings

**Numbered indicators** (like `DamageViewer` dots) appear on active regions showing the count of diagnoses.

### 3. BodySystemCard.tsx

Collapsible card component for each body system. Structure:

```
┌─────────────────────────────────────────────────────┐
│ 🦴 Musculoskeletal (MSK)               [Moderate ●] │
│ ─────────────────────────────────────────────────── │
│ ▼ Osteoarthritis, bilateral knees          dx 2019  │
│   Status: Active                            p.14 22 │
│                                                      │
│   Treatments:                                        │
│   • 2021-06  Kinesiotherapy follow-up          p.18  │
│   • 2020-03  Cortisone injections              p.15  │
│                                                      │
│   Consults:                                          │
│   • 2019-11  Orthopedics — bilateral OA        p.14  │
│                                                      │
│   Imaging:                                           │
│   • 2025-01  X-ray spine/sacrum — no prog.     p.8   │
│   • 2022     X-ray hip — mild OA               p.19  │
│                                                      │
│ ▶ Mild hip osteoarthritis                  dx 2022  │
└─────────────────────────────────────────────────────┘
```

- Each diagnosis is collapsible (first one expanded by default)
- Page references are rendered as `PageRefBadge` components
- Severity badge in the header

### 4. PageRefBadge.tsx

Small clickable badge component:

```tsx
// Renders: [p.8] as a small slate-colored badge
// On click: closes the deep dive modal, sets activeView to 'source',
//           and passes the page number to SourcePagesPanel
<PageRefBadge page={8} onClick={handlePageNav} />
```

Implementation leverages the existing `sourcePageNumber` state in `WorkbenchView.tsx` and the `setActiveView('source')` mechanism.

### 5. PendingInvestigationsCard.tsx

Prominent card with red/amber left border, shown at the top of the detail panel:

```
┌─ 🔴 ──────────────────────────────────────────────┐
│  PENDING INVESTIGATIONS                             │
│                                                      │
│  ⚠ 2025-01  Unsatisfactory PAP in Sep 2024 —       │
│    repeated today, red circle on cervix, ask         │
│    Gynecologist for opinion                  p.8     │
│    Type: referral  |  Urgency: HIGH                  │
│                                                      │
│  📋 2025-07  Mammogram pending Aug 2025      p.3     │
│    Type: imaging  |  Urgency: medium                 │
└─────────────────────────────────────────────────────┘
```

---

## Backend Changes

### 1. New Prompts in `app/personas.py`

Add five new subsections directly to `UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]`:
- `body_system_review`
- `pending_investigations`
- `last_office_visit`
- `abnormal_labs`
- `latest_vitals`

These are first-class analysis prompts, executed alongside existing medical summary prompts during `/analyze`.

### 2. New Prompts in `prompts/prompts.json`

Add the five subsections under the existing `"medical_summary"` key with the language/measurement standardization preamble. The prompts loader picks them up automatically alongside `family_history`, `hypertension`, etc.

### 3. Processing Orchestration

Deep dive prompts run as part of the standard `POST /api/applications/{id}/analyze` flow. When `/analyze` processes the `medical_summary` section, it now iterates over all 10 subsections (5 existing + 5 new deep dive).

**Parallelization**: The 5 new prompts are independent of each other and independent of the existing 5 prompts, so all 10 `medical_summary` subsections can run concurrently:

```python
# In processing.py — all medical_summary prompts run in parallel
results = await asyncio.gather(
    # Existing prompts
    run_prompt("family_history", context),
    run_prompt("hypertension", context),
    run_prompt("high_cholesterol", context),
    run_prompt("other_medical_findings", context),
    run_prompt("other_risks", context),
    # New deep dive prompts
    run_prompt("body_system_review", context),
    run_prompt("pending_investigations", context),
    run_prompt("last_office_visit", context),
    run_prompt("abnormal_labs", context),
    run_prompt("latest_vitals", context),
)
```

**Note on analysis time**: The 5 new prompts run in parallel with existing prompts, so the wall-clock impact is minimal — bounded by the slowest individual prompt, not the sum. The `body_system_review` prompt is the most complex and may take 15–30 seconds, which runs concurrently with existing analysis.

### 4. LLMOutputs Type Extension

In `app/personas.py`, the `medical_summary` section now contains all 10 subsections, all populated by `/analyze`:

```python
"medical_summary": {
    # Existing prompts:
    "family_history": ...,
    "hypertension": ...,
    "high_cholesterol": ...,
    "other_medical_findings": ...,
    "other_risks": ...,
    # New deep dive prompts (also populated by /analyze):
    "body_system_review": ...,
    "pending_investigations": ...,
    "last_office_visit": ...,
    "abnormal_labs": ...,
    "latest_vitals": ...,
}
```

All 10 subsections are written together during a single `/analyze` call.

### 5. Frontend Type Extension

In `frontend/src/lib/types.ts`, extend `LLMOutputs`:

```typescript
export interface LLMOutputs {
  // ... existing ...
  medical_summary?: {
    // ... existing subsections ...
    body_system_review?: SubsectionOutput;
    pending_investigations?: SubsectionOutput;
    last_office_visit?: SubsectionOutput;
    abnormal_labs?: SubsectionOutput;
    latest_vitals?: SubsectionOutput;
    [key: string]: SubsectionOutput | undefined;
  };
}
```

---

## Page Reference Navigation Flow

```
User clicks [p.8] badge in Deep Dive Modal
        │
        ▼
PageRefBadge.onClick(8)
        │
        ▼
BodySystemDeepDiveModal calls onNavigateToPage(8)
        │
        ▼
WorkbenchView receives callback:
  1. setIsDeepDiveOpen(false)    — close modal
  2. setSourcePageNumber(8)      — set target page
  3. setActiveView('source')     — switch to source view
        │
        ▼
SourceReviewView loads with initialPage=8
        │
        ▼
PDF viewer scrolls to page 8
```

This leverages the existing `sourcePageNumber` state already in `WorkbenchView`.

---

## UI Mockup — Deep Dive Modal

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ✕  Body System Deep Dive — Case #5005316b                        [Export PDF]  │
├─────────────────────┬───────────────────────────────────────────────────────────┤
│                     │                                                           │
│    ┌───────┐        │  🔴 PENDING INVESTIGATIONS                                │
│    │  ● ●  │ Head   │  ┌──────────────────────────────────────────────────────┐ │
│    │  \_/  │        │  │ ⚠ 2025-01 — Unsatisfactory PAP, red circle on      │ │
│    │   |   │        │  │   cervix, ask Gynecologist for opinion       [p.8]   │ │
│    │  /█\  │ Chest  │  └──────────────────────────────────────────────────────┘ │
│    │  /█\  │        │                                                           │
│    │   █   │ Abdom. │  📋 LAST OFFICE VISIT & LABS                              │
│    │  / \  │ Pelvis │  ┌──────────────────────────────────────────────────────┐ │
│    │ /   \ │        │  │ LOV: 2025-07 — Mammogram pending Aug 2025,          │ │
│    │/     \│ Legs   │  │ routine bloodwork due. Repeat colonoscopy 2028.     │ │
│    │       │        │  │ F/u physical Sep 2025.               [p.3] [p.4]    │ │
│    └───────┘        │  │                                                      │ │
│                     │  │ Last Labs: 2024-08 — Essentially normal [p.12]       │ │
│   Legend:           │  └──────────────────────────────────────────────────────┘ │
│   ● High concern    │                                                           │
│   ● Moderate        │  🫁 ENT (Ear/Nose/Throat)                     [Low ●]    │
│   ● Low/Stable      │  ┌──────────────────────────────────────────────────────┐ │
│   ○ No findings     │  │ ▼ Tinnitus                            dx 2023-05    │ │
│                     │  │   Mild hearing loss, non-throbbing        [p.12]     │ │
│   3 body systems    │  │   No treatment per hearing test                      │ │
│   with findings     │  └──────────────────────────────────────────────────────┘ │
│                     │                                                           │
│                     │  🦴 MSK (Musculoskeletal)                [Moderate ●]     │
│                     │  ┌──────────────────────────────────────────────────────┐ │
│                     │  │ ▼ Osteoarthritis, bilateral knees     dx 2019       │ │
│                     │  │   Status: Active                 [p.14] [p.22]      │ │
│                     │  │   Treatments:                                        │ │
│                     │  │   • 2021-06 Kinesiotherapy follow-up       [p.18]    │ │
│                     │  │   • 2020-03 Cortisone injections           [p.15]    │ │
│                     │  │   Imaging:                                            │ │
│                     │  │   • 2025-01 X-ray spine/sacrum — no prog. [p.8]     │ │
│                     │  │   • 2022    X-ray hip — mild OA           [p.19]    │ │
│                     │  │                                                      │ │
│                     │  │ ▶ Mild hip OA                         dx 2022       │ │
│                     │  └──────────────────────────────────────────────────────┘ │
│                     │                                                           │
│                     │  ... (GU, GI, BUILD sections follow) ...                  │
│                     │                                                           │
│                     │  🔬 ABNORMAL LAB RESULTS                                  │
│                     │  ┌──────────────────────────────────────────────────────┐ │
│                     │  │ (If any abnormal labs found, listed here)            │ │
│                     │  └──────────────────────────────────────────────────────┘ │
│                     │                                                           │
│                     │  💓 LATEST VITALS                                         │
│                     │  ┌──────────────────────────────────────────────────────┐ │
│                     │  │ BP: 128/82  HR: 72  Weight: 160 lbs  BMI: 27.4     │ │
│                     │  │ Date: 2025-01                             [p.7]      │ │
│                     │  └──────────────────────────────────────────────────────┘ │
│                     │                                                           │
│                     │  👨‍👩‍👧‍👦 FAMILY HISTORY                                       │
│                     │  ┌──────────────────────────────────────────────────────┐ │
│                     │  │ • Brother — colon cancer (age 52, deceased)  [p.5]   │ │
│                     │  │ • Brother — colonic polyps (40s)            [p.5]   │ │
│                     │  │ • Father — melanomas x2                     [p.6]   │ │
│                     │  │ • Brother — metastatic carcinoid syndrome,  [p.6]   │ │
│                     │  │   spread to brain                                    │ │
│                     │  └──────────────────────────────────────────────────────┘ │
├─────────────────────┴───────────────────────────────────────────────────────────┤
│                               Powered by AI Analysis                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

Each phase includes its own tests. Tests are written alongside the implementation, not deferred to a later phase.

### Phase 1: Backend — Prompts & API (Est. 3–4 days)

| Task | Description | Files |
|------|-------------|-------|
| 1.1 | Add 5 new prompt templates to `UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]` | `app/personas.py` |
| 1.2 | Add 5 new prompt templates to `prompts/prompts.json` under `medical_summary` (with standardization preamble) | `prompts/prompts.json` |
| 1.3 | Update `/analyze` processing to include the 5 new prompts in the `medical_summary` parallel batch | `app/processing.py` |
| 1.4 | Enhance family history prompt with page references for deep dive display | `app/processing.py` |

**Phase 1 Tests:**

| Test | Description | File |
|------|-------------|------|
| T1.1 | Verify `UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]` contains all 10 subsection keys (5 existing + 5 new) | `tests/test_deep_dive_prompts.py` |
| T1.2 | Verify each new prompt has a non-empty `prompt` string and `description` | `tests/test_deep_dive_prompts.py` |
| T1.3 | Unit test: `/analyze` processing runs all 10 `medical_summary` prompts in parallel and returns correct structure | `tests/test_deep_dive_processing.py` |
| T1.4 | Unit test: after `/analyze`, `llm_outputs.medical_summary` contains all 5 new deep dive subsection keys | `tests/test_deep_dive_processing.py` |
| T1.5 | API test: `POST /api/applications/{id}/analyze` populates deep dive data in `llm_outputs` (mock LLM) | `tests/test_deep_dive_api.py` |
| T1.6 | API test: `GET /api/applications/{id}` returns deep dive data under `llm_outputs.medical_summary.*` | `tests/test_deep_dive_api.py` |
| T1.7 | Verify deep dive results survive round-trip persist → load | `tests/test_deep_dive_api.py` |
| T1.8 | Verify each new prompt template produces valid JSON when given sample APS markdown (`@pytest.mark.integration`) | `tests/test_deep_dive_integration.py` |

### Phase 2: Frontend — Types & Modal Shell (Est. 2–3 days)

| Task | Description | Files |
|------|-------------|-------|
| 2.1 | Add TypeScript interfaces for deep dive data | `frontend/src/lib/types.ts` |
| 2.2 | Add helper `getDeepDiveData(app)` that reads deep dive sections from existing `llm_outputs` | `frontend/src/lib/api.ts` |
| 2.3 | Create `BodySystemDeepDiveModal.tsx` shell (layout, open/close, loading/error/empty states) | `frontend/src/components/` |
| 2.4 | Add "Deep Dive" button to `PatientSummary.tsx` | `frontend/src/components/PatientSummary.tsx` |
| 2.5 | Wire modal state (`isDeepDiveOpen`) in `WorkbenchView.tsx` | `frontend/src/components/WorkbenchView.tsx` |

**Phase 2 Tests:**

| Test | Description | File |
|------|-------------|------|
| T2.1 | Component test: `PatientSummary` renders "Deep Dive" button when application has completed analysis | `frontend/src/__tests__/PatientSummary.test.tsx` |
| T2.2 | Component test: clicking "Deep Dive" button calls the `onDeepDive` handler | `frontend/src/__tests__/PatientSummary.test.tsx` |
| T2.3 | Component test: `BodySystemDeepDiveModal` renders in open state, closes on Escape/X/backdrop click | `frontend/src/__tests__/BodySystemDeepDiveModal.test.tsx` |
| T2.4 | Component test: `BodySystemDeepDiveModal` shows "Run Analysis" message when no `llm_outputs` data exists | `frontend/src/__tests__/BodySystemDeepDiveModal.test.tsx` |
| T2.5 | Component test: `BodySystemDeepDiveModal` shows "Re-run Analysis" button for legacy apps missing deep dive data | `frontend/src/__tests__/BodySystemDeepDiveModal.test.tsx` |
| T2.6 | Helper test: `getDeepDiveData` correctly extracts deep dive sections from `llm_outputs` | `frontend/src/__tests__/api.test.ts` |

### Phase 3: Frontend — Body Diagram (Est. 2–3 days)

| Task | Description | Files |
|------|-------------|-------|
| 3.1 | Create `BodyDiagram.tsx` — SVG human silhouette with clickable regions | `frontend/src/components/` |
| 3.2 | Implement region highlighting based on body system severity data | `frontend/src/components/BodyDiagram.tsx` |
| 3.3 | Add click handlers that scroll right panel to corresponding body system section | `frontend/src/components/BodyDiagram.tsx` |
| 3.4 | Add hover tooltips showing system name + severity, and a color legend | `frontend/src/components/BodyDiagram.tsx` |

**Phase 3 Tests:**

| Test | Description | File |
|------|-------------|------|
| T3.1 | Component test: `BodyDiagram` renders SVG with correct number of highlighted regions for given body systems | `frontend/src/__tests__/BodyDiagram.test.tsx` |
| T3.2 | Component test: regions with no findings are dimmed/not clickable | `frontend/src/__tests__/BodyDiagram.test.tsx` |
| T3.3 | Component test: clicking a highlighted region calls `onRegionClick` with the correct system code | `frontend/src/__tests__/BodyDiagram.test.tsx` |
| T3.4 | Component test: severity color mapping is correct (high→red, moderate→amber, low→green) | `frontend/src/__tests__/BodyDiagram.test.tsx` |
| T3.5 | Snapshot test: `BodyDiagram` SVG output matches expected structure for a known set of body systems | `frontend/src/__tests__/BodyDiagram.test.tsx` |

### Phase 4: Frontend — Detail Cards (Est. 3–4 days)

| Task | Description | Files |
|------|-------------|-------|
| 4.1 | Create `PageRefBadge.tsx` — clickable page number badge | `frontend/src/components/` |
| 4.2 | Create `PendingInvestigationsCard.tsx` — highlighted pending items | `frontend/src/components/` |
| 4.3 | Create `LastOfficeVisitCard.tsx` — LOV + last labs summary | `frontend/src/components/` |
| 4.4 | Create `BodySystemCard.tsx` — collapsible diagnoses with treatments/consults/imaging | `frontend/src/components/` |
| 4.5 | Create `AbnormalLabsCard.tsx` — chronological abnormal lab list | `frontend/src/components/` |
| 4.6 | Create `LatestVitalsCard.tsx` — vitals snapshot grid | `frontend/src/components/` |
| 4.7 | Integrate family history (reuse/enhance `FamilyHistoryPanel`) | `frontend/src/components/` |

**Phase 4 Tests:**

| Test | Description | File |
|------|-------------|------|
| T4.1 | Component test: `PageRefBadge` renders page number, calls `onClick` with correct page | `frontend/src/__tests__/PageRefBadge.test.tsx` |
| T4.2 | Component test: `PendingInvestigationsCard` renders all pending items with urgency badges and page refs | `frontend/src/__tests__/PendingInvestigationsCard.test.tsx` |
| T4.3 | Component test: `PendingInvestigationsCard` shows empty state when no pending investigations | `frontend/src/__tests__/PendingInvestigationsCard.test.tsx` |
| T4.4 | Component test: `LastOfficeVisitCard` renders LOV date, summary, follow-up plans, and last labs | `frontend/src/__tests__/LastOfficeVisitCard.test.tsx` |
| T4.5 | Component test: `BodySystemCard` renders system header with severity badge, diagnoses list is collapsible | `frontend/src/__tests__/BodySystemCard.test.tsx` |
| T4.6 | Component test: `BodySystemCard` first diagnosis expanded by default, others collapsed | `frontend/src/__tests__/BodySystemCard.test.tsx` |
| T4.7 | Component test: `BodySystemCard` renders treatments, consults, and imaging in reverse chronological order | `frontend/src/__tests__/BodySystemCard.test.tsx` |
| T4.8 | Component test: `AbnormalLabsCard` renders labs with value, unit, reference range, and interpretation | `frontend/src/__tests__/AbnormalLabsCard.test.tsx` |
| T4.9 | Component test: `LatestVitalsCard` renders BP, HR, weight, BMI; handles null values gracefully | `frontend/src/__tests__/LatestVitalsCard.test.tsx` |
| T4.10 | Component test: All detail cards pass page references to `PageRefBadge` correctly | `frontend/src/__tests__/DetailCards.integration.test.tsx` |

### Phase 5: Integration — Page Navigation & Polish (Est. 2–3 days)

| Task | Description | Files |
|------|-------------|-------|
| 5.1 | Wire `PageRefBadge` → `WorkbenchView` → `SourcePagesPanel` navigation | Multiple |
| 5.2 | Handle modal close + view switch + page scroll sequence | `WorkbenchView.tsx` |
| 5.3 | Loading states, error handling, empty states for all components | All new components |
| 5.4 | PDF export for deep dive (similar to `PolicyReportModal`) | `BodySystemDeepDiveModal.tsx` |
| 5.5 | Responsive design and accessibility | All new components |

**Phase 5 Tests:**

| Test | Description | File |
|------|-------------|------|
| T5.1 | Integration test: clicking `PageRefBadge` in modal → modal closes → source view opens at correct page | `frontend/src/__tests__/DeepDiveNavigation.integration.test.tsx` |
| T5.2 | Integration test: deep dive modal populates immediately from `llm_outputs` after analysis completes | `frontend/src/__tests__/DeepDiveNavigation.integration.test.tsx` |
| T5.3 | Integration test: "Re-run Analysis" button triggers `/analyze`, updates displayed data including deep dive | `frontend/src/__tests__/DeepDiveNavigation.integration.test.tsx` |
| T5.4 | Component test: PDF export generates printable HTML with all sections | `frontend/src/__tests__/BodySystemDeepDiveModal.test.tsx` |
| T5.5 | Accessibility test: modal traps focus, Escape closes, all interactive elements are keyboard-navigable | `frontend/src/__tests__/BodySystemDeepDiveModal.a11y.test.tsx` |

### Phase 6: End-to-End Validation (Est. 2 days)

| Task | Description | Files |
|------|-------------|-------|
| 6.1 | E2E test: full flow from app load → run analysis → click Deep Dive → results display → page nav works | `tests/e2e/test_deep_dive_e2e.py` |
| 6.2 | Validate against pilot user's ground truth example (case #5005316b) | `tests/test_deep_dive_ground_truth.py` |
| 6.3 | Test with 3+ real APS documents of varying length and complexity | `tests/test_deep_dive_integration.py` |
| 6.4 | Performance test: `/analyze` with deep dive prompts completes within 90 seconds for a 50-page APS | `tests/test_deep_dive_performance.py` |
| 6.5 | Regression test: existing `llm_outputs` sections (customer_profile, family_history, etc.) still produce correct output after adding deep dive prompts | `tests/test_analyze_regression.py` |

**Total Estimated Effort: 14–17 days**

---

## API Contract

### POST /api/applications/{id}/analyze (existing — extended)

The existing `/analyze` endpoint now runs the 5 new deep dive prompts in addition to existing prompts. No new endpoint is needed.

**Behavior change**: After analysis completes, `application.llm_outputs.medical_summary` contains 10 subsections (5 existing + 5 new). The response shape is unchanged — deep dive data is accessed via the standard `GET /api/applications/{id}` response under `llm_outputs.medical_summary.body_system_review`, `.pending_investigations`, `.last_office_visit`, `.abnormal_labs`, and `.latest_vitals`.

**Deep dive data location in GET response**:

```json
{
  "llm_outputs": {
    "medical_summary": {
      "family_history": { "section": "medical_summary", "subsection": "family_history", "raw": "...", "parsed": { ... } },
      "hypertension": { ... },
      "high_cholesterol": { ... },
      "other_medical_findings": { ... },
      "other_risks": { ... },
      "body_system_review": { "section": "medical_summary", "subsection": "body_system_review", "raw": "...", "parsed": { "body_systems": [ ... ] } },
      "pending_investigations": { "section": "medical_summary", "subsection": "pending_investigations", "raw": "...", "parsed": { "pending_investigations": [ ... ], "summary": "..." } },
      "last_office_visit": { "section": "medical_summary", "subsection": "last_office_visit", "raw": "...", "parsed": { "last_office_visit": { ... }, "last_labs": { ... } } },
      "abnormal_labs": { "section": "medical_summary", "subsection": "abnormal_labs", "raw": "...", "parsed": { "abnormal_labs": [ ... ] } },
      "latest_vitals": { "section": "medical_summary", "subsection": "latest_vitals", "raw": "...", "parsed": { "latest_vitals": { ... } } }
    }
  }
}
```

---

## Design Decisions

### Why deep dive runs as part of `/analyze` (not a separate endpoint)

1. **Single workflow** — Underwriters expect all analysis to be ready when they open an application; a separate step adds friction
2. **Minimal wall-clock impact** — The 5 new prompts run in parallel with the existing 5, so total analysis time increases only by the delta of the slowest new prompt vs. the existing slowest prompt
3. **Data consistency** — All medical summary data is generated from the same extraction snapshot in one pass; no risk of stale or mismatched analysis states
4. **Simpler architecture** — No new endpoint, no separate trigger button, no separate loading state to manage
5. **Always available** — Deep dive data is always ready when the underwriter clicks "Deep Dive" on the Patient Summary; no waiting

### Why a human body diagram instead of just a list?

1. **Pilot user request** — Explicitly asked for something "similar to how auto claims page shows a car bird's eye view"
2. **Visual scanning** — Underwriters can immediately see which systems are affected
3. **Pattern recognition** — Multiple findings in one region (e.g., GI + hepatic) are visually apparent
4. **Engagement** — Interactive diagrams improve discoverability vs. long scrollable lists

### Why per-section prompts instead of one large prompt?

1. **JSON reliability** — Smaller JSON schemas = fewer parsing errors from the LLM
2. **Parallelization** — 5 prompts can run concurrently, reducing wall-clock time
3. **Selective re-runs** — Can re-run just one section if results are unsatisfactory
4. **Token budget** — Each prompt fits within a single context window comfortably

---

## Validation Criteria

The implementation should be validated against the pilot user's ground truth example (case #5005316b). The deep dive output should capture at minimum:

- [ ] **Pending investigations**: PAP repeat, gynecologist referral
- [ ] **LOV**: 2025-Jul visit with mammogram pending, colonoscopy repeat 2028, Saxenda follow-up
- [ ] **Last labs**: 2024-Aug, essentially normal
- [ ] **GU system**: PAP results (2025-Jan), unsatisfactory PAP (2024-Sep) with cervix finding
- [ ] **MSK system**: OA dx 2019, bilateral knees, cortisone injections, kinesiotherapy, X-ray spine 2025, hip OA 2022
- [ ] **BUILD**: Saxenda for weight loss, lost 50lbs from 210lbs, stress eating/caregiver
- [ ] **ENT**: Tinnitus dx 2023-May, mild hearing loss, no treatment
- [ ] **GI**: Colonoscopy 2023-Aug, diverticulosis, repeat in 5 years
- [ ] **Family history**: Brother colon cancer (52, deceased), brother colonic polyps (40s), father melanomas x2, brother metastatic carcinoid syndrome (brain)
- [ ] **Page references**: Every finding has at least one page reference that matches the source document

---

## Open Questions

1. **Family history prompt** — Should we create a new deep-dive-specific family history prompt with page references, or enhance the existing `medical_summary.family_history` prompt? Recommendation: Enhance the existing prompt to include page references and structured relative data, so the deep dive modal can reuse family history from the standard analysis.

2. **Large document handling** — For 50+ page APS documents that use the large document processor with batch summaries, should the deep dive prompts run against the condensed context or the full markdown? Recommendation: Use condensed context but include source page numbers from the original batches.

3. **Legacy applications** — Applications analyzed before this feature existed will lack deep dive data. The modal should detect this and offer a "Re-run Analysis" button that re-triggers `/analyze` to generate the missing deep dive sections.

4. **Body diagram fidelity** — How detailed should the SVG silhouette be? Simple outline (like the car) or more anatomically detailed? Recommendation: Start with a clean, simple front-facing silhouette with clearly defined clickable regions. Avoid anatomical complexity.
