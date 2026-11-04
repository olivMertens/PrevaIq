'use client';

import { useEffect, useState } from 'react';
import { Layers } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getAnalyzerSchema } from '@/lib/api';
import { textValue } from '@/lib/applicationDisplay';
import type { FieldSchema } from '@/lib/types';
import { DOSSIER_FIELDS, getFieldLabel } from './propertyClaimHelpers';

interface DataTabProps {
  extractedFields: Record<string, unknown>;
  derivedFields: Array<{ name: string; value: string }>;
  persona: string;
}

interface FieldRow {
  key: string;
  label: string;
  value: string;
  confidence?: number;
}

/** Every extracted field (insured/policy first, then the claim) and the analyzer schema. */
export default function DataTab({ extractedFields, derivedFields, persona }: DataTabProps) {
  const t = useTranslations('claims');
  const tc = useTranslations('caseCockpit.dataTab');
  const [showSchema, setShowSchema] = useState(false);
  const [schema, setSchema] = useState<FieldSchema | null>(null);

  useEffect(() => {
    if (!showSchema || schema) return;
    getAnalyzerSchema(persona).then(setSchema).catch(() => {});
  }, [showSchema, schema, persona]);

  const rows: FieldRow[] = Object.entries(extractedFields).flatMap(([key, raw]) => {
    const field = raw as { field_name?: string; value?: unknown; confidence?: number } | undefined;
    const value = (textValue(field?.value) ?? '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (!field || !value) return [];
    const name = field.field_name || key.split(':').pop() || key;
    return [{ key, label: getFieldLabel(name, t), value, confidence: field.confidence }];
  });
  const isDossier = (row: FieldRow) => DOSSIER_FIELDS.has(row.key.split(':').pop() || row.key);
  const groups = [
    { title: tc('insured'), rows: rows.filter(isDossier) },
    { title: tc('claim'), rows: rows.filter((row) => !isDossier(row)) },
  ].filter((group) => group.rows.length > 0);

  return (
    <div className="space-y-5 text-sm">
      <button
        type="button"
        onClick={() => setShowSchema((value) => !value)}
        aria-pressed={showSchema}
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-indigo-700 hover:bg-slate-50"
      >
        <Layers className="h-4 w-4" aria-hidden />
        {showSchema ? t('cuSchema.viewData') : t('cuSchema.viewSchema')}
      </button>

      {showSchema ? (
        schema ? (
          <div>
            <p className="mb-2 text-slate-500">{t('schemaFieldsDefined', { count: schema.field_count })} — <span className="font-mono">{schema.schema.name}</span></p>
            <ul className="divide-y divide-slate-100">
              {Object.entries(schema.schema.fields).map(([name, field]) => (
                <li key={name} className="flex items-start justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="font-mono font-medium text-slate-900">{name}</p>
                    <p className="text-slate-600">{field.description}</p>
                  </div>
                  <span className="flex-shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{field.type}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-slate-500">{t('cuSchema.loading')}</p>
        )
      ) : groups.length > 0 ? (
        groups.map((group) => (
          <section key={group.title}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{group.title}</h3>
            <table className="w-full">
              <tbody className="divide-y divide-slate-100">
                {group.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row" className="w-1/3 py-2 pr-4 text-left font-medium text-slate-500">{row.label}</th>
                    <td className="py-2 text-slate-900">{row.value}</td>
                    <td className="w-14 py-2 text-right text-xs text-slate-500">
                      {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      ) : derivedFields.length > 0 ? (
        <table className="w-full">
          <tbody className="divide-y divide-slate-100">
            {derivedFields.map((field) => (
              <tr key={field.name}>
                <th scope="row" className="w-1/3 py-2 pr-4 text-left font-medium text-slate-500">{field.name}</th>
                <td className="py-2 text-slate-900">{field.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-slate-500">{t('cuSchema.noFields')}</p>
      )}
    </div>
  );
}
