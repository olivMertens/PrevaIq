// API types matching the Python backend data structures

// ============================================================================
// Persona Types
// ============================================================================

/**
 * Persona definition from the backend
 */
export interface Persona {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  enabled: boolean;
}

// ============================================================================
// Application Types
// ============================================================================

export interface StoredFile {
  filename: string;
  path: string;
  url: string | null;
}

export interface ConfidenceSummary {
  total_fields: number;
  average_confidence: number;
  high_confidence_count: number;
  medium_confidence_count: number;
  low_confidence_count: number;
  high_confidence_fields: Record<string, unknown>[];
  medium_confidence_fields: Record<string, unknown>[];
  low_confidence_fields: Record<string, unknown>[];
}

export interface ExtractedField {
  field_name: string;
  value: unknown;
  confidence: number;
  page_number?: number;
  bounding_box?: number[];
  source_text?: string;
  source_file?: string;
}

export interface MarkdownPage {
  file: string;
  page_number: number;
  source_page_number?: number;
  markdown: string;
  extraction_backend?: string;
  analyzer_id?: string | null;
}

export interface ExtractionFileProvenance {
  file: string;
  media_type?: 'document' | 'image' | 'video' | 'audio' | 'unknown';
  extraction_backend?: string;
  analyzer_id?: string | null;
  fallback_from?: string | null;
  fallback_reason?: string | null;
  field_count?: number;
  page_count?: number;
  content_length?: number;
  quality_score?: number;
  attempted_engines?: string[];
  description_source?: string;
}

export interface ExtractionSegmentProvenance {
  segment_id: string;
  file: string;
  pages: number[];
  segment_type: string;
  confidence?: number;
  reasons?: string[];
  recommended_engines?: string[];
  selected_engine?: string | null;
  review_required?: boolean;
}

export interface ExtractionConflict {
  field_name: string;
  values: unknown[];
  source_segments?: string[];
  review_required?: boolean;
  reason?: string;
}

export interface ExtractionProvenance {
  pipeline?: string;
  content_understanding?: {
    api_version?: string;
    default_analyzer_id?: string;
    completion_deployment?: string | null;
    embedding_deployment?: string | null;
  };
  openai?: {
    deployment?: string;
    model?: string;
    api_version?: string;
    reasoning_effort?: string;
  };
  markitdown?: {
    enabled?: boolean;
    mode?: string;
    use_content_understanding?: boolean;
  };
  summary?: {
    file_count?: number;
    processed_file_count?: number;
    field_count?: number;
    average_confidence?: number | null;
    page_count?: number;
    last_analyzer_id?: string | null;
    selected_engine?: string | null;
    attempted_engines?: string[];
    fallback_used?: boolean;
    fallback_reason?: string | null;
    quality_scores?: Record<string, number | null>;
  };
  files?: ExtractionFileProvenance[];
  segments?: ExtractionSegmentProvenance[];
  conflicts?: ExtractionConflict[];
  review_required?: boolean;
}

export interface OrchestrationReviewReason {
  code: string;
  detail?: unknown;
}

export interface OrchestrationStageTrace {
  elapsed_seconds?: number;
  max_seconds?: number;
  tokens_used?: number;
  max_tokens?: number;
  reextractions?: number;
  max_reextractions?: number;
  skipped?: string[];
  budget_exhausted?: boolean;
  review_reasons?: OrchestrationReviewReason[];
  completed_at?: string;
}

export interface Orchestration {
  stages?: Record<string, OrchestrationStageTrace>;
  review?: {
    status: 'needs_review' | 'auto_ok' | 'reviewed';
    reasons?: OrchestrationReviewReason[];
    decision?: string;
    updated_at?: string;
  };
}

// LLM Output structures
export interface ParsedOutput {
  summary?: string;
  key_fields?: { label: string; value: string }[];
  risk_assessment?: string;
  underwriting_action?: string;
  [key: string]: unknown;
}

export interface SubsectionOutput {
  section: string;
  subsection: string;
  raw: string;
  parsed: ParsedOutput;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface LLMOutputs {
  application_summary?: {
    customer_profile?: SubsectionOutput;
    existing_policies?: SubsectionOutput;
    [key: string]: SubsectionOutput | undefined;
  };
  medical_summary?: {
    family_history?: SubsectionOutput;
    hypertension?: SubsectionOutput;
    high_cholesterol?: SubsectionOutput;
    other_medical_findings?: SubsectionOutput;
    other_risks?: SubsectionOutput;
    // Deep dive subsections (populated by /analyze)
    body_system_review?: SubsectionOutput;
    pending_investigations?: SubsectionOutput;
    last_office_visit?: SubsectionOutput;
    abnormal_labs?: SubsectionOutput;
    latest_vitals?: SubsectionOutput;
    [key: string]: SubsectionOutput | undefined;
  };
  requirements?: {
    requirements_summary?: SubsectionOutput;
    [key: string]: SubsectionOutput | undefined;
  };
  [key: string]: Record<string, SubsectionOutput | undefined> | undefined;
}

// ============================================================================
// Body System Deep Dive Types
// ============================================================================

export type BodyRegion = 'head' | 'chest' | 'abdomen' | 'pelvis' | 'joints_spine' | 'extremities' | 'skin' | 'systemic';
export type Severity = 'high' | 'moderate' | 'low' | 'normal';
export type DiagnosisStatus = 'active' | 'resolved' | 'monitoring' | 'unknown';
export type InvestigationType = 'test' | 'referral' | 'consult' | 'imaging' | 'procedure';
export type Urgency = 'high' | 'medium' | 'low';

export interface TreatmentEntry {
  description: string;
  date: string;
  page_references: number[];
}

export interface ConsultEntry {
  specialist: string;
  date: string;
  summary: string;
  page_references: number[];
}

export interface ImagingEntry {
  type: string;
  date: string;
  result: string;
  page_references: number[];
}

export interface DiagnosisEntry {
  name: string;
  date_diagnosed: string;
  status: DiagnosisStatus;
  page_references: number[];
  treatments: TreatmentEntry[];
  consults: ConsultEntry[];
  imaging: ImagingEntry[];
}

export interface BodySystemEntry {
  system_code: string;
  system_name: string;
  body_region: BodyRegion;
  severity: Severity;
  diagnoses: DiagnosisEntry[];
}

export interface BodySystemReviewParsed {
  body_systems: BodySystemEntry[];
}

export interface PendingInvestigation {
  date: string;
  description: string;
  type: InvestigationType;
  urgency: Urgency;
  page_references: number[];
}

export interface PendingInvestigationsParsed {
  pending_investigations: PendingInvestigation[];
  summary: string;
}

export interface LastOfficeVisitData {
  date: string;
  summary: string;
  follow_up_plans: string[];
  page_references: number[];
}

export interface LastLabsData {
  date: string;
  summary: string;
  page_references: number[];
}

export interface LastOfficeVisitParsed {
  last_office_visit: LastOfficeVisitData;
  last_labs: LastLabsData;
}

export interface AbnormalLabEntry {
  date: string;
  test_name: string;
  value: string;
  unit: string;
  reference_range: string;
  interpretation: string;
  page_references: number[];
}

export interface AbnormalLabsParsed {
  abnormal_labs: AbnormalLabEntry[];
}

export interface LatestVitalsData {
  date: string;
  blood_pressure: { systolic: number; diastolic: number } | null;
  heart_rate: number | null;
  weight: { value: number; unit: string } | null;
  height: { value: string; unit: string } | null;
  bmi: number | null;
  temperature: number | null;
  respiratory_rate: number | null;
  oxygen_saturation: number | null;
  page_references: number[];
}

export interface LatestVitalsParsed {
  latest_vitals: LatestVitalsData;
}

/** Aggregation of all deep dive data extracted from llm_outputs */
export interface DeepDiveData {
  bodySystemReview: BodySystemReviewParsed | null;
  pendingInvestigations: PendingInvestigationsParsed | null;
  lastOfficeVisit: LastOfficeVisitParsed | null;
  abnormalLabs: AbnormalLabsParsed | null;
  latestVitals: LatestVitalsParsed | null;
  familyHistory: ParsedOutput | null;
  hasData: boolean;
}

// Risk Analysis types (separate from standard LLM outputs)
export interface PolicyCitation {
  policy_id: string;
  criteria_id?: string;
  policy_name: string;
  matched_condition: string;
  applied_action?: string;
  rationale?: string;
}

export interface RiskFinding {
  category: string;
  finding: string;
  policy_id: string;
  criteria_id?: string;
  policy_name: string;
  matched_condition?: string;
  risk_level: string;
  action: string;
  rationale?: string;
}

export interface PremiumRecommendation {
  base_decision: string;
  loading_percentage: string;
  exclusions?: string[];
  conditions?: string[];
}

export interface RiskAnalysisResult {
  overall_risk_level: string;
  overall_rationale: string;
  findings: RiskFinding[];
  premium_recommendation: PremiumRecommendation;
  underwriting_action: string;
  confidence?: string;
  data_gaps?: string[];
}

export interface RiskAnalysis {
  timestamp?: string;
  raw?: string;
  parsed?: RiskAnalysisResult;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface BatchSummary {
  batch_num: number;
  page_start: number;
  page_end: number;
  page_count: number;
  summary: string;
}

export interface ContextLabel {
  key: string;
  label: string;
  type: 'guarantee' | 'verification' | 'severity' | 'fraud' | 'missing_doc' | 'alert';
  urgency: 'info' | 'success' | 'warning' | 'critical';
  color: string;
  icon?: string;
  tooltip?: string;
  source_url?: string;
}

export interface ContextTask {
  key: string;
  task: string;
  category: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  due_offset_days: number;
}

export interface ApplicationMetadata {
  id: string;
  created_at: string;
  external_reference: string | null;
  status: 'pending' | 'extracted' | 'completed' | 'error';
  persona?: string;
  files: StoredFile[];
  document_markdown?: string;
  markdown_pages?: MarkdownPage[];
  cu_raw_result_path?: string;
  llm_outputs?: LLMOutputs;
  extracted_fields?: Record<string, ExtractedField>;
  confidence_summary?: ConfidenceSummary;
  analyzer_id_used?: string;
  extraction_provenance?: ExtractionProvenance;
  orchestration?: Orchestration | null;
  risk_analysis?: RiskAnalysis;
  // Sentiment analysis (computed by the Sentiment Agent)
  sentiment_analysis?: {
    score: number;
    level: 'calm' | 'moderate' | 'stressed' | 'critical';
    suggestedTone?: 'empathetic' | 'standard' | 'formal';
    contextSummary?: string;
    factors?: string[];
    suggestions?: string[];
    agent?: string;
    computed_at?: string;
  } | null;
  // Fraud analysis
  fraud_analysis?: Record<string, unknown> | null;
  // Background processing status
  processing_status?: 'extracting' | 'analyzing' | 'error' | null;
  processing_error?: string | null;
  // Large document processing
  processing_mode?: 'standard' | 'large_document';
  condensed_context?: string;
  document_stats?: {
    size_bytes?: number;
    size_kb?: number;
    size_mb?: number;
    page_count?: number;
    estimated_tokens?: number;
  };
  batch_summaries?: BatchSummary[];
  // Context labels (backend-driven badges/alerts)
  context_labels?: ContextLabel[];
  // Context tasks (backend-driven action items)
  context_tasks?: ContextTask[];
  // Live Souscr'IA front-office risk context (alerts + fraud-suspicion signals),
  // keyed by external_reference == Souscr'IA thread_id. Read-only, may be absent.
  souscria_context?: SouscriaRiskContext | null;
  // Action history (persisted actions)
  action_history?: {
    action_id: string;
    label: string;
    performed: string;
    at: string;
    source: string;
    systems: string[];
    trace_summary?: { system: string; call: string; status: string }[];
  }[];
}

export interface SouscriaRiskAlert {
  severity?: string;
  category?: string;
  reason?: string;
  excerpt?: string;
  created_at?: string;
  handoff_human?: boolean;
  [key: string]: unknown;
}

export interface SouscriaRiskContext {
  thread_id: string;
  available: boolean;
  alerts: SouscriaRiskAlert[];
  alert_count: number;
  max_severity: string | null;
  fraud?: {
    score?: number;
    count?: number;
    signals?: Record<string, unknown>[];
    disclaimer?: string;
  } | null;
  fraud_score?: number | null;
  fraud_disclaimer?: string | null;
  errors?: string[];
  source?: string;
}

export interface ApplicationListItem {
  id: string;
  created_at: string;
  external_reference: string | null;
  status: string;
  persona?: string;
  summary_title?: string;
  processing_status?: 'extracting' | 'analyzing' | 'error' | null;
  protected?: boolean;
  file_count?: number;
  key_fields?: Record<string, string>;
}

// Patient/Applicant structured data derived from extracted fields
export interface PatientInfo {
  name: string;
  gender: string;
  dateOfBirth: string;
  age: number | string;
  occupation: string;
  height: string;
  weight: string;
  bmi: number | string;
}

export interface LabResult {
  name: string;
  value: string;
  unit: string;
  date?: string;
}

export interface MedicalCondition {
  name: string;
  status: string;
  date?: string;
  details?: string;
}

export interface TimelineItem {
  date: string;
  type: 'condition' | 'medication' | 'test' | 'visit';
  title: string;
  description?: string;
  icon?: string;
  color?: string;
}

// Substance use tracking (tobacco, alcohol, drugs)
export interface SubstanceUse {
  tobacco: {
    date?: string;
    status: string;
    history?: string[];
  };
  alcohol: {
    found: boolean;
    details?: string;
  };
  marijuana: {
    found: boolean;
    details?: string;
  };
  substance_abuse: {
    date?: string;
    found: boolean;
    details?: string;
  };
}

export interface FamilyHistory {
  conditions: string[];
}

export interface Allergies {
  found: boolean;
  items?: string[];
}

export interface OccupationAvocation {
  occupation?: string;
  activities?: string[];
}

// ============================================================================
// Prompt Catalog Types
// ============================================================================

/**
 * Prompts organized by section and subsection
 */
export interface PromptsData {
  prompts: Record<string, Record<string, string>>;
}

/**
 * Single prompt response
 */
export interface PromptDetail {
  section: string;
  subsection: string;
  text: string;
}

/**
 * Response when updating/creating a prompt
 */
export interface PromptUpdateResponse {
  section: string;
  subsection: string;
  text: string;
  message: string;
}

// ============================================================================
// Content Understanding Analyzer Types
// ============================================================================

/**
 * Status of the custom analyzer
 */
export interface AnalyzerStatus {
  analyzer_id: string;
  exists: boolean | null;
  analyzer: Record<string, unknown> | null;
  confidence_scoring_enabled: boolean;
  default_analyzer_id: string;
  api_version?: string;
  completion_deployment?: string | null;
  embedding_deployment?: string | null;
  markitdown?: {
    enabled: boolean;
    mode: string;
    use_content_understanding: boolean;
  };
  persona?: string;
  error?: string;
}

export interface FileFormatCapabilities {
  persona: string;
  categories: Record<string, string[]>;
  groups?: Record<string, string[]>;
  extensions?: string[];
  all_extensions: string[];
  accept: string;
}

/**
 * Information about an analyzer
 */
export interface AnalyzerInfo {
  id: string;
  type: 'prebuilt' | 'custom';
  media_type?: 'document' | 'image' | 'video';
  description: string;
  exists: boolean;
  persona?: string;
  persona_name?: string;
}

/**
 * List of available analyzers
 */
export interface AnalyzerList {
  analyzers: AnalyzerInfo[];
}

/**
 * Response when creating an analyzer
 */
export interface AnalyzerCreateResponse {
  message: string;
  analyzer_id: string;
  result: Record<string, unknown>;
}

/**
 * Field definition in the schema
 */
export interface FieldDefinition {
  type: string;
  description: string;
  method: string;
  estimateSourceAndConfidence: boolean;
}

/**
 * Schema for the custom analyzer fields
 */
export interface FieldSchema {
  schema: {
    name: string;
    fields: Record<string, FieldDefinition>;
  };
  field_count: number;
}

// ============================================================================
// Underwriting Policy Types
// ============================================================================

/**
 * Criteria within an underwriting policy
 */
export interface PolicyCriteriaItem {
  id: string;
  condition: string;
  risk_level: string;
  action: string;
  rationale: string;
}

/**
 * Modifying factor for a policy
 */
export interface ModifyingFactor {
  factor: string;
  impact: string;
}

/**
 * Underwriting policy definition
 */
export interface UnderwritingPolicy {
  id: string;
  category: string;
  subcategory: string;
  name: string;
  description: string;
  criteria: PolicyCriteriaItem[];
  modifying_factors?: ModifyingFactor[];
  references?: string[];
}

/**
 * Request to create a new policy
 */
export interface PolicyCreateRequest {
  id: string;
  category: string;
  subcategory: string;
  name: string;
  description: string;
  criteria?: PolicyCriteriaItem[];
  modifying_factors?: ModifyingFactor[];
  references?: string[];
}

/**
 * Request to update an existing policy
 */
export interface PolicyUpdateRequest {
  category?: string;
  subcategory?: string;
  name?: string;
  description?: string;
  criteria?: PolicyCriteriaItem[];
  modifying_factors?: ModifyingFactor[];
  references?: string[];
}

/**
 * Policy citation from LLM analysis
 */
export interface PolicyCitation {
  policy_id: string;
  policy_name: string;
  criteria_applied: string;
  finding: string;
  rating_impact: string;
}

/**
 * Extended parsed output with policy citations
 */
export interface ParsedOutputWithCitations extends ParsedOutput {
  policy_citations?: PolicyCitation[];
}

/**
 * Response from policy API endpoints
 */
export interface PoliciesResponse {
  policies: UnderwritingPolicy[];
  total: number;
}

export interface PolicyResponse {
  policy: UnderwritingPolicy;
  message?: string;
}

// ============================================================================
// Property Deep Dive Types (Mortgage)
// ============================================================================

export interface PropertyDeepDiveComparable {
  address: string;
  sold_price: number;
  sold_date: string;
  distance_km: number;
  bedrooms: number;
  bathrooms: number;
  living_area: number;
  price_psf: number;
  similarity_score: number;
}

export interface PropertyPriceTrend {
  area_name: string;
  avg_price_current: number;
  avg_price_1yr_ago: number;
  avg_price_3yr_ago: number;
  yoy_change_pct: number;
  cagr_3yr_pct: number;
  trend_direction: 'up' | 'down' | 'stable';
}

export interface PropertyFeature {
  category: string;
  feature: string;
  value: string;
  data_point_source?: string;
}

export interface PropertyPhoto {
  url: string;
  caption?: string;
  category: 'exterior' | 'interior' | 'aerial' | 'floorplan';
}

export interface PropertyDeepDiveData {
  property_summary: {
    address: string;
    property_type: string;
    purchase_price: number;
    appraised_value?: number;
    year_built?: number;
    lot_size?: string;
    living_area?: number;
    bedrooms?: number;
    bathrooms?: number;
    garages?: number;
    parking?: string;
  };
  risk_classification: 'low' | 'medium' | 'high';
  risk_rationale?: string;
  auto_appraisal_eligible: boolean;
  auto_appraisal_recommendation: string;
  comparable_sales: PropertyDeepDiveComparable[];
  price_trend: PropertyPriceTrend;
  property_features: PropertyFeature[];
  appraisal_data_points?: Record<string, string>;
  mls_listing_url?: string;
  mls_number?: string;
  photos: PropertyPhoto[];
  needs_physical_appraisal: boolean;
  physical_appraisal_reason?: string;
  warning?: string;
}
