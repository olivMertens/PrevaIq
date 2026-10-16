/**
 * Customer 360 TypeScript type definitions.
 * Matches the backend data models in app/customer360.py.
 */

export interface CustomerProfile {
  id: string;
  name: string;
  date_of_birth: string;
  email: string;
  phone: string;
  address: string;
  customer_since: string;
  risk_tier: 'low' | 'medium' | 'high';
  brand?: string;
  tags: string[];
  notes: string;
  souscria_ref?: string;
}

export interface CustomerJourneyEvent {
  date: string;
  persona: string;
  application_id: string;
  event_type: string;
  title: string;
  summary: string;
  status: string;
  risk_level: string | null;
  key_metrics: Record<string, string>;
}

export interface PersonaSummary {
  persona: string;
  persona_label: string;
  application_count: number;
  latest_status: string;
  risk_level: string | null;
  key_metrics: Record<string, string>;
  applications: CustomerJourneyEvent[];
}

export interface RiskCorrelation {
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  personas_involved: string[];
}

export interface SouscriaContract {
  id?: string;
  product?: string;
  formula?: string;
  vehicle?: string;
  property?: string;
  annual_premium?: number;
  monthly_premium?: number;
  status?: string;
  expiry_date?: string;
  [key: string]: unknown;
}

export interface SouscriaAdvisor {
  id?: string;
  first_name?: string;
  last_name?: string;
  agency?: string;
  experience_years?: number;
  specialization?: string[];
  global_quality_score?: number;
}

export interface SouscriaNextBestAction {
  id?: string;
  label?: string;
  reason?: string;
  priority?: string;
  action_type?: string;
  [key: string]: unknown;
}

export interface SouscriaAcquisition {
  available: boolean;
  client_id: string;
  contracts: SouscriaContract[];
  advisor?: SouscriaAdvisor | null;
  next_best_actions: SouscriaNextBestAction[];
  source: string;
}

export interface Customer360View {
  profile: CustomerProfile;
  journey_events: CustomerJourneyEvent[];
  persona_summaries: PersonaSummary[];
  risk_correlations: RiskCorrelation[];
  total_products: number;
  active_claims: number;
  overall_risk: string;
  souscria_acquisition?: SouscriaAcquisition | null;
}
