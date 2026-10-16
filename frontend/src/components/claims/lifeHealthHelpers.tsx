'use client';

import type { ExtractedField } from '@/lib/types';
import { textValue } from '@/lib/applicationDisplay';
import CitableValue from '../CitableValue';
import ConfidenceIndicator from '../ConfidenceIndicator';

export interface TimelineEntry {
  date: string;
  year: string;
  title: string;
  description?: string;
  color: 'orange' | 'yellow' | 'blue' | 'green' | 'purple' | 'red';
  details?: string;
  sortDate?: number;
}

export function parseDate(text: string): Date | null {
  if (!text) return null;
  let match = text.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]));
  match = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (match) return new Date(parseInt(match[3]), parseInt(match[1]) - 1, parseInt(match[2]));
  return null;
}

export function formatDateDisplay(date: Date | null): { date: string; year: string } {
  if (!date) return { date: 'N/A', year: '' };
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return {
    date: `${months[date.getMonth()]}-${date.getDate().toString().padStart(2, '0')}`,
    year: date.getFullYear().toString(),
  };
}

export function getFieldData(
  extractedFields: Record<string, ExtractedField> | undefined,
  keys: string[],
  fallbackValue: string = ''
): { value: string; field?: ExtractedField } {
  if (extractedFields) {
    for (const key of keys) {
      if (extractedFields[key]?.value != null && extractedFields[key]?.value !== '') {
        const value = textValue(extractedFields[key].value);
        if (value) return { value, field: extractedFields[key] };
      }
      for (const extractedKey of Object.keys(extractedFields)) {
        if (extractedKey.endsWith(`:${key}`) && extractedFields[extractedKey].value != null && extractedFields[extractedKey].value !== '') {
          const value = textValue(extractedFields[extractedKey].value);
          if (value) return { value, field: extractedFields[extractedKey] };
        }
      }
    }
  }
  return { value: fallbackValue };
}

export function formatMonetaryValue(value: string): string {
  if (!value || value === 'N/A') return 'N/A';
  if (/^\$[\d,]+\.?\d*$/.test(value.trim())) return value.trim();
  const dollarMatch = value.match(/\$[\d,]+\.?\d*/);
  if (dollarMatch) return dollarMatch[0];
  if (value.toLowerCase().includes('unknown') || value.length > 20) return 'Pending';
  return value;
}

export function FieldWithConfidence({
  data,
  className,
  formatAsMoney = false,
}: {
  data: { value: string; field?: ExtractedField };
  className?: string;
  formatAsMoney?: boolean;
}) {
  const displayValue = formatAsMoney ? formatMonetaryValue(data.value) : data.value;
  return (
    <div className="flex items-center gap-1.5">
      <CitableValue value={displayValue} citation={data.field} className={className} />
      {data.field && <ConfidenceIndicator confidence={data.field.confidence} />}
    </div>
  );
}
