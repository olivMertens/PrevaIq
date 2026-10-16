/**
 * API client for communicating with the Python backend.
 * This module provides functions to interact with the workbench backend.
 */

import type {
  ApplicationMetadata,
  ApplicationListItem,
  PatientInfo,
  LabResult,
  MedicalCondition,
  TimelineItem,
  SubstanceUse,
  FamilyHistory,
  ExtractedField,
  PromptsData,
  AnalyzerStatus,
  AnalyzerInfo,
  FieldSchema,
  FileFormatCapabilities,
  Persona,
  UnderwritingPolicy,
  PolicyCreateRequest,
  PolicyUpdateRequest,
  PoliciesResponse,
  PolicyResponse,
  DeepDiveData,
  BodySystemReviewParsed,
  PendingInvestigationsParsed,
  LastOfficeVisitParsed,
  AbnormalLabsParsed,
  LatestVitalsParsed,
  SouscriaRiskContext,
} from './types';
import { textValue } from './applicationDisplay';

// Backend API base URL - uses relative paths to go through Next.js proxy rewrites
const API_BASE_URL = '';

/**
 * Get the media base URL.
 * Returns empty string so all media requests use relative paths and route
 * through the Next.js API proxy, which injects the X-API-Key header
 * server-side. The proxy preserves binary responses (arrayBuffer) and
 * forwards Range/Content-Range headers for video streaming.
 */
function getMediaBaseUrl(): string {
  return API_BASE_URL;
}

/**
 * Get the full URL for a media file (image, video, PDF).
 * Routes through the Next.js proxy which handles authentication and
 * binary content (Content-Length, Accept-Ranges, Content-Range).
 */
export function getMediaUrl(url: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) {
    return url;
  }
  const base = getMediaBaseUrl();
  return `${base}${url.startsWith('/') ? '' : '/'}${url}`;
}

/**
 * Custom error class for API errors
 */
export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }

  get serviceDetail(): Record<string, unknown> | undefined {
    if (!this.details || typeof this.details !== 'object') return undefined;
    const detail = (this.details as Record<string, unknown>).detail;
    return detail && typeof detail === 'object' && !Array.isArray(detail)
      ? detail as Record<string, unknown>
      : undefined;
  }

  get code(): string | undefined {
    const code = this.serviceDetail?.code;
    return typeof code === 'string' ? code : undefined;
  }

  get requestId(): string | undefined {
    const id = this.serviceDetail?.request_id;
    return typeof id === 'string' && /^[a-f0-9]{32}$/.test(id) ? id : undefined;
  }
}

function getApiErrorMessage(errorData: unknown, fallback: string): string {
  if (!errorData || typeof errorData !== 'object') return fallback;
  const data = errorData as Record<string, unknown>;
  const candidate = data.detail ?? data.error ?? data.message;
  if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
  if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
    const message = (candidate as Record<string, unknown>).message;
    if (typeof message === 'string' && message.trim()) return message.trim();
  }
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    return data.detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) {
          const msg = (item as Record<string, unknown>).msg;
          return typeof msg === 'string' ? msg : '';
        }
        return '';
      })
      .filter(Boolean)
      .join(', ');
  }
  return fallback;
}

/**
 * Generic fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = getApiErrorMessage(errorData, response.statusText || `HTTP ${response.status}`);
    throw new APIError(response.status, message, errorData);
  }

  return response.json();
}

export interface ConversationRequest {
  message: string;
  conversation_id: string | null;
  persona: string;
  agent_type: string;
  use_corrections: boolean;
  language: string;
}

export interface ConversationResponse {
  conversation_id: string;
  title: string;
  response: string;
  agent?: { name: string; tools_available?: string[]; tools_called?: string[]; framework?: string };
  rag?: {
    enabled: boolean;
    citations?: { policy_id: string; policy_name: string; chunk_type: string; criteria_id?: string }[];
  };
}

export async function sendConversation(
  appId: string,
  body: ConversationRequest,
  signal: AbortSignal,
): Promise<ConversationResponse> {
  return apiFetch<ConversationResponse>(`/api/applications/${encodeURIComponent(appId)}/conversations`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  });
}

// ============================================================================
// Application Management APIs
// ============================================================================

/**
 * List all personas available in the system
 */
export async function listPersonas(): Promise<{ personas: Persona[] }> {
  return apiFetch<{ personas: Persona[] }>('/api/personas');
}

/**
 * Get a specific persona configuration
 */
export async function getPersona(personaId: string): Promise<Persona> {
  return apiFetch<Persona>(`/api/personas/${personaId}`);
}

export async function getFileFormatCapabilities(persona?: string): Promise<FileFormatCapabilities> {
  const params = persona ? `?persona=${encodeURIComponent(persona)}` : '';
  return apiFetch<FileFormatCapabilities>(`/api/capabilities/file-formats${params}`);
}

/**
 * List all applications from the backend storage, optionally filtered by persona
 */
export async function listApplications(persona?: string): Promise<ApplicationListItem[]> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch<ApplicationListItem[]>(`/api/applications${params}`);
}

/**
 * Get detailed metadata for a specific application
 */
export async function getApplication(appId: string): Promise<ApplicationMetadata> {
  return apiFetch<ApplicationMetadata>(`/api/applications/${appId}`);
}

export async function deleteApplication(appId: string): Promise<void> {
  await apiFetch(`/api/applications/${appId}`, { method: 'DELETE' });
}

/**
 * Live-refresh the Souscr'IA front-office risk context (alerts + fraud signals)
 * for a dossier. Read-only; returns null when the connector is off / the dossier
 * has no Souscr'IA thread reference.
 */
export async function getSouscriaContext(appId: string): Promise<SouscriaRiskContext | null> {
  return apiFetch<SouscriaRiskContext | null>(`/api/applications/${appId}/souscria-context`);
}

/**
 * Extract deep dive data from an application's llm_outputs.
 * No API call needed — reads from existing llm_outputs on the application object.
 * Filters out error data (subsections where parsing failed).
 */
export function getDeepDiveData(app: ApplicationMetadata): DeepDiveData {
  const ms = app.llm_outputs?.medical_summary;

  // Helper: return parsed data only if it's valid (no _error key)
  const validParsed = (subsection: any) => {
    const parsed = subsection?.parsed;
    if (!parsed || (typeof parsed === 'object' && '_error' in parsed)) return null;
    return parsed;
  };

  const bodySystemReview = (validParsed(ms?.body_system_review) as BodySystemReviewParsed | null);
  const pendingInvestigations = (validParsed(ms?.pending_investigations) as PendingInvestigationsParsed | null);
  const lastOfficeVisit = (validParsed(ms?.last_office_visit) as LastOfficeVisitParsed | null);
  const abnormalLabs = (validParsed(ms?.abnormal_labs) as AbnormalLabsParsed | null);
  const latestVitals = (validParsed(ms?.latest_vitals) as LatestVitalsParsed | null);
  const familyHistory = validParsed(ms?.family_history);

  const hasData = !!(bodySystemReview || pendingInvestigations || lastOfficeVisit || abnormalLabs || latestVitals);

  return {
    bodySystemReview,
    pendingInvestigations,
    lastOfficeVisit,
    abnormalLabs,
    latestVitals,
    familyHistory,
    hasData,
  };
}

/**
 * Create a new application with uploaded files
 */
export async function createApplication(
  files: File[],
  externalReference?: string,
  persona?: string
): Promise<ApplicationMetadata> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  if (externalReference) {
    formData.append('external_reference', externalReference);
  }
  if (persona) {
    formData.append('persona', persona);
  }

  const response = await fetch(`${API_BASE_URL}/api/applications`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = getApiErrorMessage(errorData, response.statusText || `HTTP ${response.status}`);
    throw new APIError(response.status, message, errorData);
  }

  return response.json();
}

/**
 * Add files to an existing application and optionally re-trigger processing.
 */
export async function addFilesToApplication(
  appId: string,
  files: File[],
  autoProcess: boolean = true
): Promise<{ app_id: string; new_files: number; total_files: number; processing: boolean }> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));

  const params = autoProcess ? '' : '?auto_process=false';
  const response = await fetch(`${API_BASE_URL}/api/applications/${appId}/files${params}`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const message = getApiErrorMessage(errorData, response.statusText || `HTTP ${response.status}`);
    throw new APIError(response.status, message, errorData);
  }

  return response.json();
}

/**
 * Run content understanding extraction on an application
 * @param background If true, starts in background and returns immediately
 */
export async function runContentUnderstanding(
  appId: string,
  background: boolean = false
): Promise<ApplicationMetadata> {
  const params = background ? '?background=true' : '';
  return apiFetch<ApplicationMetadata>(`/api/applications/${appId}/extract${params}`, {
    method: 'POST',
  });
}

/**
 * Run underwriting prompts analysis on an application
 * @param background If true, starts in background and returns immediately
 * @param locale Optional UI locale (fr/en) — controls LLM response language
 */
export async function runUnderwritingAnalysis(
  appId: string,
  sections?: string[],
  background: boolean = false,
  locale?: string
): Promise<ApplicationMetadata> {
  const params = background ? '?background=true' : '';
  return apiFetch<ApplicationMetadata>(`/api/applications/${appId}/analyze${params}`, {
    method: 'POST',
    body: JSON.stringify({ sections, language: locale }),
  });
}

/**
 * Run sentiment analysis (Sentiment Agent) on an application.
 * Result is stored in app_md.sentiment_analysis and returned.
 */
export async function runSentimentAnalysis(
  appId: string,
  force: boolean = false
): Promise<Record<string, unknown>> {
  const params = force ? '?force=true' : '';
  return apiFetch<Record<string, unknown>>(`/api/applications/${appId}/sentiment${params}`, {
    method: 'POST',
  });
}

/**
 * Run deep dive analysis on an application
 * @param background If true, starts in background and returns immediately
 */
export async function runDeepDiveAnalysis(
  appId: string,
  background: boolean = false,
  force: boolean = false
): Promise<ApplicationMetadata> {
  const qp = new URLSearchParams();
  if (background) qp.set('background', 'true');
  if (force) qp.set('force', 'true');
  const qs = qp.toString();
  return apiFetch<ApplicationMetadata>(`/api/applications/${appId}/analyze/deep-dive${qs ? `?${qs}` : ''}`, {
    method: 'POST',
  });
}

/**
 * Poll for deep dive analysis completion
 * @param appId Application ID
 * @param timeout Maximum time to poll in milliseconds (default: 2 minutes)
 * @param interval Polling interval in milliseconds (default: 2 seconds)
 */
export async function pollForDeepDiveCompletion(
  appId: string,
  timeout: number = 120000,
  interval: number = 2000
): Promise<ApplicationMetadata> {
  const startTime = Date.now();
  let pollCount = 0;
  
  while (true) {
    pollCount++;
    const app = await getApplication(appId);
    
    // Check for backend error state
    if (app.processing_status === 'error' || (app as any).processing_error) {
      throw new Error((app as any).processing_error || 'Deep dive analysis failed');
    }
    
    // Check if no longer analyzing (could be 'completed', 'idle', null, etc.)
    // Deep dive completes when processing_status changes from 'analyzing'
    if (app.processing_status !== 'analyzing') {
      return app;
    }
    
    // Check timeout
    if (Date.now() - startTime > timeout) {
      throw new Error('Deep dive analysis timed out');
    }
    
    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, interval));
  }
}

/**
 * Poll for application status until analysis completes or fails
 * @param appId Application ID
 * @param timeout Maximum time to poll in milliseconds (default: 5 minutes)
 * @param interval Polling interval in milliseconds (default: 2 seconds)
 */
export async function pollForAnalysisCompletion(
  appId: string,
  timeout: number = 300000,
  interval: number = 2000
): Promise<ApplicationMetadata> {
  const startTime = Date.now();
  
  while (true) {
    const app = await getApplication(appId);
    
    // Check for backend error state
    if (app.status === 'error' || app.processing_status === 'error' || (app as any).processing_error) {
      throw new Error((app as any).processing_error || 'Analysis failed');
    }
    
    // Check if completed - processing_status should be null when done
    if (app.status === 'completed') {
      return app;
    }
    
    // Check timeout
    if (Date.now() - startTime > timeout) {
      throw new Error('Analysis polling timed out');
    }
    
    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, interval));
  }
}

/**
 * Start policy-based risk analysis (underwriting) and wait for completion.
 *
 * The backend returns 202 immediately and runs the analysis in the background,
 * so the request is never held open long enough to hit the ingress timeout
 * (which previously returned a plain-text `stream timeout` body and crashed the
 * old `await response.json()` handlers). This helper kicks off the run, then
 * polls `getApplication` until `processing_status` leaves `analyzing`.
 *
 * @param appId Application ID
 * @param timeout Maximum time to poll in milliseconds (default: 5 minutes)
 * @param interval Polling interval in milliseconds (default: 2 seconds)
 * @returns The updated application once analysis completes
 */
export async function runRiskAnalysis(
  appId: string,
  timeout: number = 300000,
  interval: number = 2000
): Promise<ApplicationMetadata> {
  let response: Response;
  try {
    response = await fetch(`/api/applications/${appId}/risk-analysis`, {
      method: 'POST',
    });
  } catch (err) {
    // Network-level failure (TypeError) — e.g. connection dropped.
    throw new Error(
      "Impossible de contacter le serveur pour lancer l'analyse des risques. V\u00e9rifiez votre connexion et r\u00e9essayez."
    );
  }

  // 409 = an analysis is already running for this dossier. That's fine — just
  // fall through and poll for it to finish rather than surfacing an error.
  if (!response.ok && response.status !== 409) {
    const raw = await response.text().catch(() => '');
    let message = '';
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      message =
        (typeof parsed.detail === 'string' && parsed.detail) ||
        (typeof parsed.error === 'string' && parsed.error) ||
        (typeof parsed.message === 'string' && parsed.message) ||
        '';
    } catch {
      message = '';
    }

    // Ingress/gateway timeouts (504 / "stream timeout") get a friendly retry hint.
    if (response.status === 504 || /stream timeout/i.test(raw)) {
      throw new Error(
        "L'analyse des risques a pris trop de temps. Veuillez r\u00e9essayer."
      );
    }

    throw new Error(message || "\u00c9chec du lancement de l'analyse des risques.");
  }

  // Poll until the background task finishes (status leaves 'analyzing').
  const startTime = Date.now();
  while (true) {
    const app = await getApplication(appId);

    if (app.processing_status === 'error' || (app as any).processing_error) {
      throw new Error(
        (app as any).processing_error || "L'analyse des risques a \u00e9chou\u00e9."
      );
    }

    if (app.processing_status !== 'analyzing') {
      return app;
    }

    if (Date.now() - startTime > timeout) {
      throw new Error(
        "L'analyse des risques a pris trop de temps. Veuillez r\u00e9essayer."
      );
    }

    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}

/**
 * Start full processing (extraction + analysis) in background.
 * Returns immediately. Client should poll getApplication() for status updates.
 * @param processingMode - 'auto', 'large_document', or 'standard'
 */
export async function startProcessing(appId: string, processingMode?: string): Promise<ApplicationMetadata> {
  const url = processingMode 
    ? `/api/applications/${appId}/process?processing_mode=${processingMode}`
    : `/api/applications/${appId}/process`;
  return apiFetch<ApplicationMetadata>(url, {
    method: 'POST',
  });
}

// ============================================================================
// Data Transformation Helpers - Convert raw backend data to UI-friendly format
// ============================================================================

/**
 * Extract patient info from application metadata
 */
export function extractPatientInfo(app: ApplicationMetadata): PatientInfo {
  const fields = app.extracted_fields || {};
  
  const getValue = (key: string): string => {
    const field = Object.values(fields).find(
      (f) => f.field_name === key || f.field_name.includes(key)
    );
    return textValue(field?.value) || 'N/A';
  };

  const getNumericValue = (key: string): number | string => {
    const field = Object.values(fields).find(
      (f) => f.field_name === key || f.field_name.includes(key)
    );
    const val = field?.value;
    return typeof val === 'number' ? val : textValue(val) || 'N/A';
  };

  // Try to extract from extracted_fields first, then fall back to llm_outputs
  let name = getValue('ApplicantName');
  let dateOfBirth = getValue('DateOfBirth');
  let gender = getValue('Gender');
  let age = getNumericValue('Age');
  let occupation = getValue('Occupation');
  let height = getValue('Height');
  let weight = getValue('Weight');
  let bmi = getNumericValue('BMI');
  
  // Parse from LLM outputs if not found
  const customerProfile = app.llm_outputs?.application_summary?.customer_profile?.parsed;
  if (customerProfile) {
    const keyFields = customerProfile.key_fields || [];
    for (const kf of keyFields) {
      const label = kf.label.toLowerCase();
      if ((label.includes('name') || label.includes('nom')) && name === 'N/A') {
        name = kf.value;
      }
      if ((label.includes('birth') || label.includes('naissance')) && dateOfBirth === 'N/A') {
        dateOfBirth = kf.value;
      }
      if ((label === 'sex' || label === 'gender' || label === 'sexe' || label === 'genre') && gender === 'N/A') {
        gender = kf.value;
      }
      if ((label === 'age' || label === 'âge' || label === 'age ') && age === 'N/A') {
        age = kf.value;
      }
      if ((label.includes('occupation') || label.includes('profession') || label.includes('métier') || label.includes('metier')) && occupation === 'N/A') {
        occupation = kf.value;
      }
      if ((label.includes('height') || label.includes('taille')) && height === 'N/A') {
        height = kf.value;
      }
      if ((label.includes('weight') || label.includes('poids')) && weight === 'N/A') {
        weight = kf.value;
      }
      if ((label === 'bmi' || label === 'imc') && bmi === 'N/A') {
        bmi = kf.value;
      }
    }
  }

  return {
    name,
    gender,
    dateOfBirth,
    age,
    occupation,
    height,
    weight,
    bmi,
  };
}

/**
 * Extract lab results from application data
 */
export function extractLabResults(app: ApplicationMetadata): LabResult[] {
  const results: LabResult[] = [];
  const fields = app.extracted_fields || {};

  // Map extracted fields to lab results
  const labFieldMappings: Record<string, { name: string; unit: string }> = {
    LipidPanelResults: { name: 'Lipid Panel', unit: '' },
    BloodPressureReadings: { name: 'Blood Pressure', unit: 'mmHg' },
    PulseRate: { name: 'Pulse Rate', unit: 'bpm' },
    UrinalysisResults: { name: 'Urinalysis', unit: '' },
  };

  for (const [key, info] of Object.entries(labFieldMappings)) {
    const field = Object.values(fields).find((f) => f.field_name === key);
    const value = textValue(field?.value);
    if (value) {
      results.push({
        name: info.name,
        value,
        unit: info.unit,
      });
    }
  }

  // Also extract from medical_summary LLM outputs
  const medicalSummary = app.llm_outputs?.medical_summary;
  
  // Hypertension - BP readings
  const hypertension = medicalSummary?.hypertension?.parsed;
  if (hypertension?.bp_readings && Array.isArray(hypertension.bp_readings)) {
    for (const bp of hypertension.bp_readings as Array<{ systolic?: string; diastolic?: string; date?: string }>) {
      results.push({
        name: 'Blood Pressure',
        value: `${bp.systolic || '?'}/${bp.diastolic || '?'}`,
        unit: 'mmHg',
        date: bp.date,
      });
    }
  }

  // Cholesterol - lipid panels
  const cholesterol = medicalSummary?.high_cholesterol?.parsed;
  if (cholesterol?.lipid_panels && Array.isArray(cholesterol.lipid_panels)) {
    for (const lp of cholesterol.lipid_panels as Array<{ total_cholesterol?: number; hdl?: number; ldl?: number; date?: string }>) {
      if (lp.total_cholesterol) {
        results.push({
          name: 'Total Cholesterol',
          value: lp.total_cholesterol.toString(),
          unit: 'mg/dL',
          date: lp.date,
        });
      }
      if (lp.hdl) {
        results.push({
          name: 'HDL Cholesterol',
          value: lp.hdl.toString(),
          unit: 'mg/dL',
          date: lp.date,
        });
      }
      if (lp.ldl) {
        results.push({
          name: 'LDL Cholesterol',
          value: lp.ldl.toString(),
          unit: 'mg/dL',
          date: lp.date,
        });
      }
    }
  }

  return results;
}

/**
 * Extract medical conditions from application data
 */
export function extractMedicalConditions(app: ApplicationMetadata): MedicalCondition[] {
  const conditions: MedicalCondition[] = [];
  
  const medicalSummary = app.llm_outputs?.medical_summary;
  if (!medicalSummary) return conditions;

  // Iterate through all medical summary sections
  for (const [sectionKey, section] of Object.entries(medicalSummary)) {
    if (!section?.parsed?.conditions || !Array.isArray(section.parsed.conditions)) continue;
    
    for (const cond of section.parsed.conditions as Array<{ name?: string; status?: string; date?: string; details?: string }>) {
      conditions.push({
        name: cond.name || sectionKey,
        status: cond.status || 'Unknown',
        date: cond.date,
        details: cond.details,
      });
    }
  }

  // Also check extracted fields
  const fields = app.extracted_fields || {};
  const medicalField = Object.values(fields).find(
    (f) => f.field_name === 'MedicalConditionsSummary'
  );
  if (medicalField?.value) {
    // Parse semicolon-separated conditions
    const condText = textValue(medicalField.value) || '';
    const items = condText.split(';').map((s) => s.trim()).filter(Boolean);
    for (const item of items) {
      // Check if not already added
      if (!conditions.some((c) => c.details?.includes(item))) {
        conditions.push({
          name: 'Medical Condition',
          status: 'Documented',
          details: item,
        });
      }
    }
  }

  return conditions;
}

/**
 * Build chronological timeline from application data
 */
export function buildTimeline(app: ApplicationMetadata): TimelineItem[] {
  const items: TimelineItem[] = [];
  
  // Add conditions from medical summary
  const conditions = extractMedicalConditions(app);
  for (const cond of conditions) {
    if (cond.date) {
      items.push({
        date: cond.date,
        type: 'condition',
        title: cond.name,
        description: cond.details,
        color: 'orange',
      });
    }
  }

  // Add medications
  const fields = app.extracted_fields || {};
  const medsField = Object.values(fields).find(
    (f) => f.field_name === 'CurrentMedicationsList'
  );
  if (medsField?.value) {
    const description = textValue(medsField.value);
    if (description) {
    items.push({
      date: 'Current',
      type: 'medication',
      title: 'Medications',
      description,
      color: 'blue',
    });
    }
  }

  // Sort by date (most recent first)
  items.sort((a, b) => {
    if (a.date === 'Current') return -1;
    if (b.date === 'Current') return 1;
    return new Date(b.date).getTime() - new Date(a.date).getTime();
  });

  return items;
}

/**
 * Extract substance use information
 */
export function extractSubstanceUse(app: ApplicationMetadata): SubstanceUse {
  const fields = app.extracted_fields || {};
  
  const smokingField = Object.values(fields).find(
    (f) => f.field_name === 'SmokingStatus'
  );
  const alcoholField = Object.values(fields).find(
    (f) => f.field_name === 'AlcoholUse'
  );
  const drugField = Object.values(fields).find(
    (f) => f.field_name === 'DrugUse'
  );

  return {
    tobacco: {
      status: textValue(smokingField?.value) || 'Not found',
    },
    alcohol: {
      found: !!textValue(alcoholField?.value),
      details: textValue(alcoholField?.value) || undefined,
    },
    marijuana: {
      found: false, // Would need specific field
      details: undefined,
    },
    substance_abuse: {
      found: !!textValue(drugField?.value) && textValue(drugField?.value)?.toLowerCase() !== 'no',
      details: textValue(drugField?.value) || undefined,
    },
  };
}

/**
 * Extract family history
 */
export function extractFamilyHistory(app: ApplicationMetadata): FamilyHistory {
  const conditions: string[] = [];
  
  // Check extracted fields
  const fields = app.extracted_fields || {};
  const familyField = Object.values(fields).find(
    (f) => f.field_name === 'FamilyHistorySummary'
  );
  if (familyField?.value) {
    const items = (textValue(familyField.value) || '').split(';').map((s) => s.trim()).filter(Boolean);
    conditions.push(...items);
  }

  // Also check LLM outputs
  const familyHistory = app.llm_outputs?.medical_summary?.family_history?.parsed;
  if (familyHistory?.conditions && Array.isArray(familyHistory.conditions)) {
    for (const cond of familyHistory.conditions as Array<string | { name?: string }>) {
      const text = typeof cond === 'string' ? cond : cond.name || JSON.stringify(cond);
      if (!conditions.includes(text)) {
        conditions.push(text);
      }
    }
  }

  return { conditions };
}

/**
 * Get extracted fields with confidence scores
 */
export function getFieldsWithConfidence(app: ApplicationMetadata): ExtractedField[] {
  const fields = app.extracted_fields || {};
  return Object.values(fields)
    .filter((field) => !!textValue(field.value))
    .sort((a, b) => b.confidence - a.confidence);
}

/**
 * Convert PascalCase to snake_case
 */
function toSnakeCase(str: string): string {
  return str.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
}

/**
 * Get citation data for a specific field by name
 * Searches extracted_fields for matching field name
 * Also tries case-insensitive and snake_case matching
 */
export function getCitation(
  app: ApplicationMetadata,
  fieldName: string
): ExtractedField | undefined {
  const fields = app.extracted_fields || {};
  
  // Direct lookup by field_name property
  const direct = Object.values(fields).find(
    (f) => f.field_name === fieldName
  );
  if (direct && direct.source_file) return direct;
  
  // Try snake_case version (e.g., ApplicantName -> applicant_name)
  const snakeCase = toSnakeCase(fieldName);
  const snakeMatch = Object.values(fields).find(
    (f) => f.field_name === snakeCase
  );
  if (snakeMatch && snakeMatch.source_file) return snakeMatch;
  
  // Try case-insensitive match
  const lowerFieldName = fieldName.toLowerCase();
  const caseInsensitive = Object.values(fields).find(
    (f) => f.field_name.toLowerCase() === lowerFieldName
  );
  if (caseInsensitive && caseInsensitive.source_file) return caseInsensitive;
  
  // Try partial match (for fields prefixed with filename)
  for (const field of Object.values(fields)) {
    if ((field.field_name.endsWith(fieldName) || field.field_name.includes(fieldName)) && field.source_file) {
      return field;
    }
  }
  
  // Final fallback: return direct match even if no source_file (for confidence display)
  if (direct) return direct;
  if (snakeMatch) return snakeMatch;
  if (caseInsensitive) return caseInsensitive;
  
  return undefined;
}

/**
 * Get multiple citations by field names
 * Returns a map of fieldName -> ExtractedField
 */
export function getCitations(
  app: ApplicationMetadata,
  fieldNames: string[]
): Record<string, ExtractedField | undefined> {
  const result: Record<string, ExtractedField | undefined> = {};
  for (const name of fieldNames) {
    result[name] = getCitation(app, name);
  }
  return result;
}

/**
 * Calculate BMI from height and weight if not provided
 */
export function calculateBMI(height: string, weight: string): number | null {
  // Parse height (supports formats like "5'10\"" or "178 cm")
  let heightInMeters: number | null = null;
  
  const ftInMatch = height.match(/(\d+)'?\s*(\d+)?"/);
  if (ftInMatch) {
    const feet = parseInt(ftInMatch[1]);
    const inches = parseInt(ftInMatch[2] || '0');
    heightInMeters = (feet * 12 + inches) * 0.0254;
  } else {
    const cmMatch = height.match(/(\d+)\s*cm/i);
    if (cmMatch) {
      heightInMeters = parseInt(cmMatch[1]) / 100;
    }
  }

  // Parse weight (supports "165 lb" or "75 kg")
  let weightInKg: number | null = null;
  
  const lbMatch = weight.match(/(\d+)\s*lb/i);
  if (lbMatch) {
    weightInKg = parseInt(lbMatch[1]) * 0.453592;
  } else {
    const kgMatch = weight.match(/(\d+)\s*kg/i);
    if (kgMatch) {
      weightInKg = parseInt(kgMatch[1]);
    }
  }

  if (heightInMeters && weightInKg) {
    return Math.round((weightInKg / (heightInMeters * heightInMeters)) * 10) / 10;
  }

  return null;
}

// ============================================================================
// Prompt Catalog APIs
// ============================================================================

/**
 * Get all prompts organized by section and subsection
 */
export async function getPrompts(persona?: string): Promise<PromptsData> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch<PromptsData>(`/api/prompts${params}`);
}

/**
 * Get a specific prompt by section and subsection
 */
export async function getPrompt(
  section: string,
  subsection: string,
  persona?: string
): Promise<{ section: string; subsection: string; text: string }> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch(`/api/prompts/${section}/${subsection}${params}`);
}

/**
 * Update a specific prompt
 */
export async function updatePrompt(
  section: string,
  subsection: string,
  text: string,
  persona?: string
): Promise<{ section: string; subsection: string; text: string; message: string }> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch(`/api/prompts/${section}/${subsection}${params}`, {
    method: 'PUT',
    body: JSON.stringify({ text }),
  });
}

/**
 * Create a new prompt
 */
export async function createPrompt(
  section: string,
  subsection: string,
  text: string,
  persona?: string
): Promise<{ section: string; subsection: string; text: string; message: string }> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch(`/api/prompts/${section}/${subsection}${params}`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

/**
 * Delete a prompt (resets to default)
 */
export async function deletePrompt(
  section: string,
  subsection: string,
  persona?: string
): Promise<{ message: string }> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch(`/api/prompts/${section}/${subsection}${params}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Content Understanding Analyzer APIs
// ============================================================================

/**
 * Get the status of the custom analyzer
 */
export async function getAnalyzerStatus(persona?: string): Promise<AnalyzerStatus> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch<AnalyzerStatus>(`/api/analyzer/status${params}`);
}

/**
 * Get the field schema for the custom analyzer
 */
export async function getAnalyzerSchema(persona?: string): Promise<FieldSchema> {
  const params = persona ? `?persona=${persona}` : '';
  return apiFetch<FieldSchema>(`/api/analyzer/schema${params}`);
}

/**
 * List all available analyzers
 */
export async function listAnalyzers(): Promise<{ analyzers: AnalyzerInfo[] }> {
  return apiFetch<{ analyzers: AnalyzerInfo[] }>('/api/analyzer/list');
}

/**
 * Create or update the custom analyzer
 */
export async function createAnalyzer(
  analyzerId?: string,
  persona?: string,
  description?: string,
  mediaType?: string
): Promise<{ message: string; analyzer_id: string; result: Record<string, unknown> }> {
  return apiFetch('/api/analyzer/create', {
    method: 'POST',
    body: JSON.stringify({
      analyzer_id: analyzerId,
      persona,
      description,
      media_type: mediaType,
    }),
  });
}

/**
 * Delete a custom analyzer
 */
export async function deleteAnalyzer(
  analyzerId: string
): Promise<{ message: string }> {
  return apiFetch(`/api/analyzer/${analyzerId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// Underwriting Policy APIs
// ============================================================================

/**
 * Get all policies for a persona (underwriting or claims)
 */
export async function getPolicies(persona?: string): Promise<PoliciesResponse> {
  const params = persona ? `?persona=${encodeURIComponent(persona)}` : '';
  return apiFetch<PoliciesResponse>(`/api/policies${params}`);
}

/**
 * Get a specific policy by ID
 */
export async function getPolicy(policyId: string, persona?: string): Promise<UnderwritingPolicy> {
  const params = persona ? `?persona=${encodeURIComponent(persona)}` : '';
  return apiFetch<UnderwritingPolicy>(`/api/policies/${policyId}${params}`);
}

/**
 * Get policies by category
 */
export async function getPoliciesByCategory(category: string): Promise<PoliciesResponse & { category: string }> {
  return apiFetch<PoliciesResponse & { category: string }>(`/api/policies/category/${category}`);
}

/**
 * Create a new policy
 */
export async function createPolicy(policy: PolicyCreateRequest): Promise<PolicyResponse> {
  return apiFetch<PolicyResponse>('/api/policies', {
    method: 'POST',
    body: JSON.stringify(policy),
  });
}

/**
 * Update an existing policy
 */
export async function updatePolicy(policyId: string, update: PolicyUpdateRequest): Promise<PolicyResponse> {
  return apiFetch<PolicyResponse>(`/api/policies/${policyId}`, {
    method: 'PUT',
    body: JSON.stringify(update),
  });
}

/**
 * Delete a policy
 */
export async function deletePolicy(policyId: string): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>(`/api/policies/${policyId}`, {
    method: 'DELETE',
  });
}

// ============================================================================
// RAG Index Management APIs
// ============================================================================

export interface ReindexResponse {
  status: string;
  policies_indexed?: number;
  chunks_stored?: number;
  total_time_seconds?: number;
  error?: string;
}

export interface IndexStats {
  status: string;
  total_chunks?: number;
  chunk_count?: number;  // Alternative field name used by some endpoints
  policy_count?: number;
  chunks_by_type?: Record<string, number>;
  chunks_by_category?: Record<string, number>;
  table?: string;
  last_updated?: string;
  message?: string;
  error?: string;
}

/**
 * Reindex all policies for RAG search (persona-aware)
 * @param persona - The persona to reindex policies for (underwriting, life_health_claims, automotive_claims, property_casualty_claims)
 * @param force - Whether to force delete existing chunks before reindexing
 */
export async function reindexAllPolicies(force: boolean = true, persona: string = 'underwriting'): Promise<ReindexResponse> {
  return apiFetch<ReindexResponse>(`/api/admin/policies/reindex?persona=${encodeURIComponent(persona)}`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  });
}

/**
 * Reindex a single policy
 */
export async function reindexPolicy(policyId: string): Promise<ReindexResponse> {
  return apiFetch<ReindexResponse>(`/api/admin/policies/${policyId}/reindex`, {
    method: 'POST',
  });
}

/**
 * Get RAG index statistics (persona-aware)
 * @param persona - The persona to get index stats for
 */
export async function getIndexStats(persona: string = 'underwriting'): Promise<IndexStats> {
  return apiFetch<IndexStats>(`/api/admin/policies/index-stats?persona=${encodeURIComponent(persona)}`);
}

// ============================================================================
// Claims Policy Admin APIs (Deprecated - use reindexAllPolicies/getIndexStats with persona param)
// ============================================================================

/**
 * @deprecated Use reindexAllPolicies(force, 'automotive_claims') instead
 */
export async function reindexClaimsPolicies(force: boolean = true): Promise<ReindexResponse> {
  return reindexAllPolicies(force, 'automotive_claims');
}

/**
 * @deprecated Use getIndexStats('automotive_claims') instead
 */
export async function getClaimsIndexStats(): Promise<IndexStats> {
  return getIndexStats('automotive_claims');
}

// ============================================================================
// Glossary APIs
// ============================================================================

/**
 * Glossary term structure
 */
export interface GlossaryTerm {
  abbreviation: string;
  meaning: string;
  context?: string;
  examples?: string[];
  category?: string;
  category_id?: string;
}

/**
 * Glossary category structure
 */
export interface GlossaryCategory {
  id: string;
  name: string;
  terms: GlossaryTerm[];
}

/**
 * Persona glossary structure
 */
export interface PersonaGlossary {
  persona: string;
  name: string;
  description: string;
  categories: GlossaryCategory[];
  total_terms: number;
}

/**
 * Glossary summary for listing
 */
export interface GlossarySummary {
  persona: string;
  name: string;
  description: string;
  term_count: number;
  category_count: number;
}

/**
 * List all available glossaries
 */
export async function listGlossaries(): Promise<{ glossaries: GlossarySummary[] }> {
  return apiFetch<{ glossaries: GlossarySummary[] }>('/api/glossary');
}

/**
 * Get the full glossary for a specific persona
 */
export async function getGlossary(persona: string): Promise<PersonaGlossary> {
  return apiFetch<PersonaGlossary>(`/api/glossary/${persona}`);
}

/**
 * Search for terms in a glossary
 */
export async function searchGlossary(
  persona: string,
  query: string,
  category?: string
): Promise<{ results: GlossaryTerm[]; count: number }> {
  const params = new URLSearchParams({ q: query });
  if (category) params.append('category', category);
  return apiFetch<{ results: GlossaryTerm[]; count: number }>(
    `/api/glossary/${persona}/search?${params.toString()}`
  );
}

/**
 * Create a new glossary category
 */
export async function createGlossaryCategory(
  persona: string,
  id: string,
  name: string
): Promise<{ category: GlossaryCategory; message: string }> {
  return apiFetch<{ category: GlossaryCategory; message: string }>(
    `/api/glossary/${persona}/categories`,
    {
      method: 'POST',
      body: JSON.stringify({ id, name }),
    }
  );
}

/**
 * Update a glossary category
 */
export async function updateGlossaryCategory(
  persona: string,
  categoryId: string,
  name: string
): Promise<{ category: GlossaryCategory; message: string }> {
  return apiFetch<{ category: GlossaryCategory; message: string }>(
    `/api/glossary/${persona}/categories/${categoryId}`,
    {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }
  );
}

/**
 * Delete a glossary category (must be empty)
 */
export async function deleteGlossaryCategory(
  persona: string,
  categoryId: string
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/api/glossary/${persona}/categories/${categoryId}`,
    { method: 'DELETE' }
  );
}

/**
 * Create a new glossary term
 */
export async function createGlossaryTerm(
  persona: string,
  categoryId: string,
  term: Omit<GlossaryTerm, 'category' | 'category_id'>
): Promise<{ term: GlossaryTerm; message: string }> {
  return apiFetch<{ term: GlossaryTerm; message: string }>(
    `/api/glossary/${persona}/terms/${categoryId}`,
    {
      method: 'POST',
      body: JSON.stringify(term),
    }
  );
}

/**
 * Update an existing glossary term
 */
export async function updateGlossaryTerm(
  persona: string,
  abbreviation: string,
  updates: Partial<GlossaryTerm>
): Promise<{ term: GlossaryTerm; message: string }> {
  return apiFetch<{ term: GlossaryTerm; message: string }>(
    `/api/glossary/${persona}/terms/${encodeURIComponent(abbreviation)}`,
    {
      method: 'PUT',
      body: JSON.stringify(updates),
    }
  );
}

/**
 * Delete a glossary term
 */
export async function deleteGlossaryTerm(
  persona: string,
  abbreviation: string
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(
    `/api/glossary/${persona}/terms/${encodeURIComponent(abbreviation)}`,
    { method: 'DELETE' }
  );
}

/**
 * Get formatted glossary for prompt injection
 */
export async function getFormattedGlossary(
  persona: string,
  options?: {
    maxTerms?: number;
    categories?: string[];
    formatType?: 'markdown' | 'list';
    includeHeaders?: boolean;
  }
): Promise<{ formatted: string }> {
  const params = new URLSearchParams();
  if (options?.maxTerms) params.append('max_terms', options.maxTerms.toString());
  if (options?.categories) params.append('categories', options.categories.join(','));
  if (options?.formatType) params.append('format_type', options.formatType);
  if (options?.includeHeaders !== undefined) params.append('include_headers', options.includeHeaders.toString());
  
  const queryString = params.toString();
  return apiFetch<{ formatted: string }>(
    `/api/glossary/${persona}/formatted${queryString ? `?${queryString}` : ''}`
  );
}

// ============================================================================
// Automotive Claims API
// ============================================================================

/**
 * Submit a new automotive claim
 */
export interface ClaimSubmitRequest {
  claimant_name: string;
  policy_number: string;
  incident_date: string;
  incident_description: string;
  vehicle_info?: {
    make?: string;
    model?: string;
    year?: number;
    vin?: string;
  };
}

export interface ClaimSubmitResponse {
  claim_id: string;
  status: string;
  message: string;
  created_at: string;
}

export async function submitClaim(data: ClaimSubmitRequest): Promise<ClaimSubmitResponse> {
  return apiFetch<ClaimSubmitResponse>('/api/claims/submit', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Upload files to a claim
 */
export interface FileUploadResponse {
  claim_id: string;
  uploaded_files: Array<{
    file_id: string;
    filename: string;
    content_type: string;
    size: number;
    status: string;
  }>;
  processing_status: string;
}

export async function uploadClaimFiles(claimId: string, files: File[]): Promise<FileUploadResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  // Use relative path to go through Next.js proxy
  const response = await fetch(`/api/claims/${claimId}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new APIError(
      response.status,
      errorData.detail || `Upload failed: ${response.status}`,
      errorData
    );
  }

  return response.json();
}

/**
 * Get claim processing status
 */
export interface ProcessingStatusResponse {
  claim_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  current_step?: string;
  steps_completed: string[];
  error?: string;
}

export async function getClaimProcessingStatus(claimId: string): Promise<ProcessingStatusResponse> {
  return apiFetch<ProcessingStatusResponse>(`/api/claims/${claimId}/status`);
}

/**
 * Get full claim assessment
 */
export interface DamageArea {
  area_id: string;
  location: string;
  severity: 'minor' | 'moderate' | 'severe' | 'total_loss';
  confidence: number;
  estimated_cost: number;
  description: string;
  bounding_box?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  source_media_id?: string;
}

export interface LiabilityAssessment {
  fault_determination: string;
  fault_percentage: number;
  contributing_factors: string[];
  liability_notes: string;
}

export interface FraudIndicator {
  indicator_type: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
  confidence: number;
}

export interface PolicyCitationClaim {
  policy_id: string;
  policy_name: string;
  section: string;
  citation_text: string;
  relevance_score: number;
  supports_coverage: boolean;
}

export interface PayoutRecommendation {
  recommended_amount: number;
  min_amount: number;
  max_amount: number;
  breakdown: Record<string, number>;
  adjustments: Array<{
    reason: string;
    amount: number;
  }>;
}

export interface ClaimAssessmentResponse {
  claim_id: string;
  status: string;
  overall_severity: 'minor' | 'moderate' | 'severe' | 'total_loss';
  total_estimated_damage: number;
  damage_areas: DamageArea[];
  liability: LiabilityAssessment;
  fraud_indicators: FraudIndicator[];
  policy_citations: PolicyCitationClaim[];
  payout_recommendation: PayoutRecommendation;
  adjuster_decision?: {
    decision: 'approve' | 'adjust' | 'deny' | 'investigate';
    adjusted_amount?: number;
    notes?: string;
    decided_at?: string;
    decided_by?: string;
  };
  created_at: string;
  updated_at: string;
}

export async function getClaimAssessment(claimId: string): Promise<ClaimAssessmentResponse> {
  return apiFetch<ClaimAssessmentResponse>(`/api/claims/${claimId}/assessment`);
}

/**
 * Update adjuster decision
 */
export interface AdjusterDecisionRequest {
  decision: 'approve' | 'adjust' | 'deny' | 'investigate';
  adjusted_amount?: number;
  notes?: string;
}

export interface AdjusterDecisionResponse {
  claim_id: string;
  decision: string;
  adjusted_amount?: number;
  notes?: string;
  decided_at: string;
  message: string;
}

export async function updateAdjusterDecision(
  claimId: string,
  decision: AdjusterDecisionRequest
): Promise<AdjusterDecisionResponse> {
  return apiFetch<AdjusterDecisionResponse>(`/api/claims/${claimId}/assessment/decision`, {
    method: 'PUT',
    body: JSON.stringify(decision),
  });
}

/**
 * Search claims policies
 */
export interface ClaimsPolicySearchRequest {
  query: string;
  category?: string;
  limit?: number;
}

export interface ClaimsPolicySearchResult {
  chunk_id: string;
  policy_id: string;
  policy_name: string;
  category: string;
  content: string;
  similarity?: number;  // From backend
  score?: number;       // Legacy/alias
  severity?: string;
  criteria_id?: string;
  section?: string;     // Legacy field for old components
}

export interface ClaimsPolicySearchResponse {
  query: string;
  results: ClaimsPolicySearchResult[];
  total_results: number;
}

export async function searchClaimsPolicies(
  request: ClaimsPolicySearchRequest
): Promise<ClaimsPolicySearchResponse> {
  return apiFetch<ClaimsPolicySearchResponse>('/api/claims/policies/search', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Get claim media list
 */
export interface MediaItem {
  media_id: string;
  filename: string;
  content_type: string;
  media_type: 'image' | 'video' | 'document';
  size: number;
  thumbnail_url?: string;
  url: string;
  processed: boolean;
  analysis_summary?: string;
  uploaded_at: string;
}

export interface ClaimMediaListResponse {
  claim_id: string;
  media_items: MediaItem[];
  total_count: number;
}

export async function getClaimMedia(claimId: string): Promise<ClaimMediaListResponse> {
  return apiFetch<ClaimMediaListResponse>(`/api/claims/${claimId}/media`);
}

/**
 * Get video keyframes
 */
export interface Keyframe {
  keyframe_id: string;
  timestamp: number;
  timestamp_formatted: string;
  thumbnail_url: string;
  description?: string;
  damage_detected: boolean;
  damage_areas?: DamageArea[];
  confidence: number;
}

export interface KeyframesResponse {
  media_id: string;
  duration: number;
  keyframes: Keyframe[];
  total_keyframes: number;
}

export async function getVideoKeyframes(claimId: string, mediaId: string): Promise<KeyframesResponse> {
  return apiFetch<KeyframesResponse>(`/api/claims/${claimId}/media/${mediaId}/keyframes`);
}

/**
 * Get damage areas for specific media
 */
export interface MediaDamageAreasResponse {
  media_id: string;
  damage_areas: DamageArea[];
  total_estimated_cost: number;
}

export async function getMediaDamageAreas(
  claimId: string,
  mediaId: string
): Promise<MediaDamageAreasResponse> {
  return apiFetch<MediaDamageAreasResponse>(`/api/claims/${claimId}/media/${mediaId}/damage-areas`);
}

// ============================================================================
// Property Deep Dive APIs (Mortgage)
// ============================================================================

/**
 * Get property deep dive analysis for a mortgage application
 */
export async function getPropertyDeepDive(appId: string): Promise<import('./types').PropertyDeepDiveData> {
  return apiFetch<import('./types').PropertyDeepDiveData>(`/api/mortgage/applications/${appId}/property-deep-dive`);
}

/**
 * Run property deep dive analysis
 */
export async function runPropertyDeepDive(appId: string, force: boolean = false): Promise<import('./types').PropertyDeepDiveData> {
  const params = force ? '?force=true' : '';
  return apiFetch<import('./types').PropertyDeepDiveData>(`/api/mortgage/applications/${appId}/property-deep-dive${params}`, {
    method: 'POST',
  });
}

// =============================================================================
// Feedback API
// =============================================================================

export interface FeedbackPayload {
  agent_type: string;
  feedback_type: 'positive' | 'negative' | 'correction';
  original_query?: string;
  agent_response?: string;
  correction?: string;
  persona?: string;
  session_id?: string;
  conversation_id?: string;
  application_id?: string;
}

export async function submitFeedback(payload: FeedbackPayload): Promise<{ status: string; feedback_id: string }> {
  return apiFetch<{ status: string; feedback_id: string }>('/api/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// =============================================================================
// Corrections API (few-shot store)
// =============================================================================

export interface Correction {
  example_id: string;
  persona: string;
  agent_type: string;
  query: string;
  bad_response: string;
  good_response: string;
  active: boolean;
  has_embedding: boolean;
  metadata: {
    source_id?: string;
    source?: string;
    category?: string;
    policy_ref?: string;
    risk_level?: string;
    corrected_by?: string;
    correction_date?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface CorrectionStats {
  total: number;
  active: number;
  with_embedding: number;
  personas: number;
  agent_types: number;
  by_category: Record<string, number>;
}

export async function fetchCorrections(params?: {
  persona?: string;
  agent_type?: string;
  category?: string;
  active?: boolean;
  limit?: number;
}): Promise<{ corrections: Correction[]; count: number }> {
  const searchParams = new URLSearchParams();
  if (params?.persona) searchParams.set('persona', params.persona);
  if (params?.agent_type) searchParams.set('agent_type', params.agent_type);
  if (params?.category) searchParams.set('category', params.category);
  if (params?.active !== undefined) searchParams.set('active', String(params.active));
  if (params?.limit) searchParams.set('limit', String(params.limit));
  const qs = searchParams.toString();
  return apiFetch<{ corrections: Correction[]; count: number }>(`/api/corrections${qs ? `?${qs}` : ''}`);
}

export async function fetchCorrectionStats(): Promise<CorrectionStats> {
  return apiFetch<CorrectionStats>('/api/corrections/stats');
}

// ============================================================================
// Fraud Detection APIs
// ============================================================================

export interface ImageFraudResult {
  filename: string;
  authenticity_score: number;
  is_likely_authentic: boolean;
  manipulation_indicators: Array<{
    indicator: string;
    confidence: number;
    description?: string;
  }>;
  filename_concordance?: {
    filename_is_descriptive: boolean;
    matches_content: boolean | null;
    expected_content?: string;
    actual_content?: string;
    note?: string;
  };
  error?: string;
}

export interface DeclarationVerification {
  overall_consistent: boolean;
  consistency_score: number;
  discrepancies: Array<{
    aspect: string;
    declared: string;
    observed: string;
    severity: string;
  }>;
  visual_observations: string[];
}

export interface FraudAttentionItem {
  priority: 'high' | 'medium' | 'low';
  label: string;
  detail: string;
}

export interface FraudOverallAssessment {
  overall_fraud_risk: 'LOW' | 'MODERATE' | 'HIGH';
  risk_score: number;
  siu_referral_recommended: boolean;
  siu_referral_reason?: string;
  attention_items?: FraudAttentionItem[];
  fraud_indicators: Array<{
    indicator_type: string;
    severity: string;
    description: string;
    confidence?: number;
  }>;
  dossier_concordance?: {
    overall_match: boolean;
    score: number;
    field_checks: Array<{
      field: string;
      declared: string;
      observed: string;
      match: boolean;
    }>;
  };
  summary: string;
}

export interface WebIntelligenceFinding {
  category?: string;
  title?: string;
  summary?: string;
  source_url?: string;
  supports_claim?: boolean;
  relevance?: string;
  // Alternative keys returned by Foundry Agent
  type?: string;
  details?: string;
  description?: string;
  source?: string;
}

export interface WebIntelligenceResult {
  event_verified?: boolean | null;
  confidence?: number | string;
  findings?: (WebIntelligenceFinding | string)[];
  source_urls?: string[];
  overall_assessment?: string;
  error?: string;
}

export interface FraudAnalysisResponse {
  application_id: string;
  image_analyses: ImageFraudResult[];
  declaration_verification?: DeclarationVerification;
  overall_assessment?: FraudOverallAssessment;
  web_intelligence?: WebIntelligenceResult;
  analysis_timestamp: string;
}

export async function runFraudAnalysis(
  claimId: string,
  filename?: string,
  reasoningEffort: 'low' | 'medium' | 'high' = 'medium',
): Promise<FraudAnalysisResponse> {
  const params = new URLSearchParams();
  if (filename) params.set('filename', filename);
  params.set('reasoning_effort', reasoningEffort);
  const qs = params.toString();
  return apiFetch<FraudAnalysisResponse>(`/api/claims/${claimId}/fraud-analysis${qs ? `?${qs}` : ''}`, {
    method: 'POST',
  });
}

export async function getFraudAnalysis(claimId: string): Promise<FraudAnalysisResponse | null> {
  try {
    return await apiFetch<FraudAnalysisResponse>(`/api/claims/${claimId}/fraud-analysis`);
  } catch {
    return null; // 404 — no saved analysis
  }
}
