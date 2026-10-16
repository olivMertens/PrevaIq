/**
 * Data Worksheet Component
 * 
 * Displays canonical mortgage data with provenance tracking:
 * - Borrower information
 * - Income details
 * - Property details
 * - Loan terms
 * - Liabilities
 * 
 * Each field shows value, confidence, and source citations.
 */

'use client';

import React, { useState } from 'react';
import {
  User, Euro, Building, FileText,
  ChevronDown, ChevronRight
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { formatCurrency, formatRatio } from './format';
import {
  formatEmploymentType,
  formatPropertyType,
  formatOccupancy,
  formatDownPaymentSource,
  formatRateType,
} from './enumLabels';
import type {
  MortgageBorrower,
  MortgageIncome,
  MortgageProperty,
  MortgageLoan,
  MortgageLiabilities,
  FieldCitation,
} from './MortgageWorkbench';
import ConfidenceIndicator from '../ConfidenceIndicator';
import CitableValue from '../CitableValue';

interface DataWorksheetProps {
  borrower: MortgageBorrower;
  coBorrower?: MortgageBorrower;
  income: MortgageIncome;
  property: MortgageProperty;
  loan: MortgageLoan;
  liabilities: MortgageLiabilities;
  fieldCitations?: Record<string, FieldCitation>;
}

interface DataField {
  label: string;
  value: string | number;
  fieldName?: string;
  isCalculated?: boolean;
}

interface DataSection {
  id: string;
  title: string;
  icon: typeof User;
  fields: DataField[];
}

export default function DataWorksheet({
  borrower,
  coBorrower,
  income,
  property,
  loan,
  liabilities,
  fieldCitations = {},
}: DataWorksheetProps) {
  const t = useTranslations('mortgageLabels');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['borrower', 'income', 'property', 'loan', 'liabilities'])
  );

  const toggleSection = (sectionId: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
    }
    setExpandedSections(newExpanded);
  };

  // Helper to get citation for a field
  const getCitation = (fieldName?: string): FieldCitation | undefined => {
    if (!fieldName) return undefined;
    return fieldCitations[fieldName];
  };

  const sections: DataSection[] = [
    {
      id: 'borrower',
      title: t('sectionBorrower'),
      icon: User,
      fields: [
        { label: t('name'), value: borrower.name, fieldName: 'BorrowerName' },
        { label: t('coBorrowerLabel'), value: borrower.co_borrower_name || 'N/A', fieldName: 'CoBorrowerName' },
        { label: t('creditScore'), value: borrower.credit_score, fieldName: 'CreditScore' },
        { label: t('employmentType'), value: formatEmploymentType(borrower.employment_type) || 'CDI', fieldName: 'EmploymentStatus' },
        { label: t('employer'), value: borrower.employer_name || t('notSpecified'), fieldName: 'EmployerName' },
        { label: t('occupation'), value: borrower.occupation || t('notSpecified'), fieldName: 'OccupationTitle' },
      ],
    },
    {
      id: 'income',
      title: t('sectionIncome'),
      icon: Euro,
      fields: [
        { label: t('primaryBorrowerIncome'), value: formatCurrency(income.primary_borrower_income || income.annual_salary || 0), fieldName: 'BaseSalary' },
        { label: t('coBorrowerIncome'), value: formatCurrency(income.co_borrower_income || 0), fieldName: 'CoBorrowerIncome' },
        { label: t('totalAnnualIncome'), value: formatCurrency(income.total_annual_income), isCalculated: true },
        { label: t('monthlyIncome'), value: formatCurrency(income.monthly_income || income.total_annual_income / 12), isCalculated: true },
      ],
    },
    {
      id: 'property',
      title: t('sectionProperty'),
      icon: Building,
      fields: [
        { label: t('address'), value: property.address, fieldName: 'PropertyAddress' },
        { label: t('purchasePrice'), value: formatCurrency(property.purchase_price), fieldName: 'PurchasePrice' },
        { label: t('appraisedValue'), value: formatCurrency(property.appraised_value || property.purchase_price), fieldName: 'AppraisedValue' },
        { label: t('propertyType'), value: formatPropertyType(property.property_type), fieldName: 'PropertyType' },
        { label: t('occupancy'), value: formatOccupancy(property.occupancy) || t('ownerOccupied'), fieldName: 'PropertyOccupancy' },
      ],
    },
    {
      id: 'loan',
      title: t('sectionLoan'),
      icon: FileText,
      fields: [
        { label: t('loanAmount'), value: formatCurrency(loan.amount), fieldName: 'RequestedLoanAmount' },
        { label: t('downPayment'), value: formatCurrency(loan.down_payment), fieldName: 'DownPaymentAmount' },
        { label: t('downPaymentPct'), value: formatRatio(loan.down_payment / property.purchase_price), isCalculated: true },
        { label: t('downPaymentSource'), value: formatDownPaymentSource(loan.down_payment_source) || t('savings'), fieldName: 'DownPaymentSource' },
        { label: t('amortization'), value: `${loan.amortization_years} ${t('years')}`, fieldName: 'AmortizationYears' },
        { label: t('contractRateLabel'), value: `${loan.contract_rate || loan.rate}%`, fieldName: 'ContractRate' },
        { label: t('term'), value: formatRateType(loan.term) || `${loan.term_years || 5} ${t('years')}`, fieldName: 'RateTerm' },
      ],
    },
    {
      id: 'liabilities',
      title: t('sectionLiabilities'),
      icon: Euro,
      fields: [
        { label: t('propertyTaxes'), value: formatCurrency(liabilities.property_taxes_monthly), isCalculated: true },
        { label: t('heating'), value: formatCurrency(liabilities.heating_monthly), isCalculated: true },
        { label: t('condoFees'), value: formatCurrency(liabilities.condo_fees_monthly || 0), fieldName: 'CondoFees' },
        { label: t('otherDebts'), value: formatCurrency(liabilities.other_debts_monthly || 0), fieldName: 'OtherDebtsMonthly' },
      ],
    },
  ];

  return (
    <div className="space-y-4">
      {sections.map((section) => {
        const isExpanded = expandedSections.has(section.id);
        const Icon = section.icon;

        return (
          <div key={section.id} className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <button
              onClick={() => toggleSection(section.id)}
              className="w-full px-4 py-3 flex items-center gap-3 hover:bg-slate-50 transition-colors"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-slate-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-slate-400" />
              )}
              <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
                <Icon className="w-4 h-4 text-emerald-600" />
              </div>
              <span className="flex-1 text-left font-medium text-slate-900">
                {section.title}
              </span>
            </button>

            {isExpanded && (
              <div className="px-4 pb-4">
                <div className="divide-y divide-slate-100">
                  {section.fields.map((field, idx) => {
                    const citation = getCitation(field.fieldName);
                    
                    return (
                      <div key={idx} className="py-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-slate-600">{field.label}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Value with citation tooltip */}
                          {citation ? (
                            <CitableValue
                              value={field.value}
                              citation={{
                                field_name: citation.field_name,
                                value: citation.value,
                                confidence: citation.confidence || 0,
                                source_file: citation.source_file,
                                page_number: citation.page_number || undefined,
                                source_text: citation.source_text || undefined,
                                bounding_box: citation.bounding_box || undefined,
                              }}
                              className="text-sm font-medium text-slate-900"
                            />
                          ) : (
                            <span className="text-sm font-medium text-slate-900">{field.value}</span>
                          )}
                          
                          {/* Confidence indicator */}
                          {citation?.confidence !== undefined && (
                            <ConfidenceIndicator 
                              confidence={citation.confidence} 
                              fieldName={field.label}
                            />
                          )}
                          
                          {/* Calculated badge for computed fields */}
                          {field.isCalculated && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                              {t('calculated')}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Co-Borrower Section */}
      {coBorrower && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 flex items-center gap-3 bg-slate-50">
            <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
              <User className="w-4 h-4 text-blue-600" />
            </div>
            <span className="font-medium text-slate-900">{t('coBorrowerInfo')}</span>
          </div>
          <div className="px-4 py-4">
            <div className="divide-y divide-slate-100">
              <div className="py-3 flex items-center justify-between">
                <span className="text-sm text-slate-600">{t('name')}</span>
                <div className="flex items-center gap-2">
                  {fieldCitations['CoBorrowerName'] ? (
                    <CitableValue
                      value={coBorrower.name}
                      citation={{
                        field_name: 'CoBorrowerName',
                        value: coBorrower.name,
                        confidence: fieldCitations['CoBorrowerName'].confidence || 0,
                        source_file: fieldCitations['CoBorrowerName'].source_file,
                        page_number: fieldCitations['CoBorrowerName'].page_number || undefined,
                      }}
                      className="text-sm font-medium text-slate-900"
                    />
                  ) : (
                    <span className="text-sm font-medium text-slate-900">{coBorrower.name}</span>
                  )}
                  {fieldCitations['CoBorrowerName']?.confidence !== undefined && (
                    <ConfidenceIndicator 
                      confidence={fieldCitations['CoBorrowerName'].confidence} 
                      fieldName="Co-Borrower Name"
                    />
                  )}
                </div>
              </div>
              <div className="py-3 flex items-center justify-between">
                <span className="text-sm text-slate-600">{t('creditScore')}</span>
                <span className="text-sm font-medium text-slate-900">{coBorrower.credit_score}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
