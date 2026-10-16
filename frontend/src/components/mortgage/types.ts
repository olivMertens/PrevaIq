/**
 * Shared types for mortgage underwriting components.
 */

export interface MortgageBorrower {
  name: string;
  first_name?: string;
  last_name?: string;
  co_borrower_name?: string;
  credit_score: number;
  employment_type?: string;
  employer_name?: string;
  occupation?: string;
  years_employed?: number;
}

export interface MortgageIncome {
  primary_borrower_income?: number;
  co_borrower_income?: number;
  annual_salary?: number;
  other_income?: number;
  total_annual_income: number;
  monthly_income?: number;
}

export interface MortgageProperty {
  address: string;
  purchase_price: number;
  appraised_value?: number;
  property_type: string;
  occupancy?: string;
}

export interface MortgageLoan {
  amount: number;
  down_payment: number;
  down_payment_source?: string;
  amortization_years: number;
  contract_rate?: number;
  rate?: number;
  qualifying_rate?: number;
  term?: string;
  term_years?: number;
}

export interface MortgageLiabilities {
  property_taxes_monthly: number;
  heating_monthly: number;
  condo_fees_monthly?: number;
  other_debts_monthly?: number;
}

export interface MortgageRatios {
  gds: number;
  tds: number;
  ltv: number;
}

export interface MortgageStressRatios {
  gds: number;
  tds: number;
  qualifying_rate: number;
}

export interface MortgageFinding {
  rule_id?: string;
  type?: string;
  severity?: 'pass' | 'warning' | 'fail' | 'info';
  category?: string;
  message: string;
  evidence?: {
    calculated_value?: number;
    limit?: number;
    source?: string;
  };
  source_file?: string;
  confidence?: number;
  sources?: string[];
}

export interface RiskSignal {
  id: string;
  category: string;
  severity: 'low' | 'medium' | 'high';
  title: string;
  description: string;
  source_documents?: string[];
}

export interface FieldCitation {
  field_name: string;
  value?: string | number | null;
  confidence?: number;
  source_file?: string;
  page_number?: number | null;
  source_text?: string | null;
  bounding_box?: number[] | null;
}

export interface MortgageApplication {
  application_id: string;
  borrower: MortgageBorrower;
  co_borrower?: MortgageBorrower;
  income: MortgageIncome;
  property: MortgageProperty;
  loan: MortgageLoan;
  liabilities: MortgageLiabilities;
  ratios: MortgageRatios;
  stress_ratios: MortgageStressRatios;
  decision: 'APPROVE' | 'DECLINE' | 'REFER';
  findings: MortgageFinding[];
  risk_signals: RiskSignal[];
  documents?: MortgageDocument[];
  narrative?: string;
  policy_checks_count?: number;
  field_citations?: Record<string, FieldCitation>;
}

export interface MortgageDocument {
  id: string;
  type: string;
  filename: string;
  uploaded_at: string;
  status: 'pending' | 'processed' | 'error';
  url?: string;
  fields_extracted?: number;
  confidence?: number;
}
