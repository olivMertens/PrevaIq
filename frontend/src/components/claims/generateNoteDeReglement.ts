'use client';

/**
 * Generate a "Note de règlement" PDF for habitation claims.
 * Uses a print-ready HTML window that the user can save as PDF.
 *
 * Locale-aware: pass `t` (scoped to `claims.report.note`) and `locale`
 * from the calling React component so the generated report follows
 * the active UI language.
 */

import { brand } from '@/lib/brand';

type Translator = (key: string, params?: Record<string, string | number | Date>) => string;

interface NoteDeReglementData {
  applicationId: string;
  insuredName: string;
  policyNumber: string;
  claimNumber: string;
  claimDate: string;
  causeOfLoss: string;
  propertyAddress: string;
  lineOfBusiness: string;
  totalEstimated: string;
  deductible: string;
  settlementAmount: string;
  aiSummary: string;
  extractedFields: Record<string, { field_name?: string; value?: unknown; confidence?: number }>;
  llmOutputs: Record<string, unknown>;
  files: { filename: string }[];
  tasks: { task: string; done: boolean }[];
}

function formatDate(date: Date, locale: string): string {
  const intlLocale = locale === 'en' ? 'en-US' : 'fr-FR';
  return date.toLocaleDateString(intlLocale, { day: '2-digit', month: 'long', year: 'numeric' });
}

function extractSummariesFromLLM(llmOutputs: Record<string, unknown>): string[] {
  const summaries: string[] = [];
  for (const [section, subsections] of Object.entries(llmOutputs)) {
    if (!subsections || typeof subsections !== 'object') continue;
    for (const [subsection, val] of Object.entries(subsections as Record<string, unknown>)) {
      const sub = val as { parsed?: { summary?: string }; raw?: string } | undefined;
      if (sub?.parsed?.summary) {
        summaries.push(`**${section} / ${subsection}** : ${sub.parsed.summary}`);
      } else if (sub?.raw && typeof sub.raw === 'string') {
        summaries.push(`**${section} / ${subsection}** : ${sub.raw.slice(0, 300)}${sub.raw.length > 300 ? '...' : ''}`);
      }
    }
  }
  return summaries;
}

function extractFieldsTable(
  extractedFields: Record<string, { field_name?: string; value?: unknown; confidence?: number }>,
  t: Translator,
): string {
  const rows: string[] = [];
  for (const [key, val] of Object.entries(extractedFields)) {
    if (!val || val.value == null || val.value === '') continue;
    const name = val.field_name || key.split(':').pop() || key;
    rows.push(`<tr><td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;color:#475569;">${name}</td><td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;font-weight:500;">${String(val.value)}</td></tr>`);
  }
  if (rows.length === 0) return `<p style="color:#94a3b8;font-style:italic;">${t('noFields')}</p>`;
  return `<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#f1f5f9;"><th style="padding:8px 12px;text-align:left;font-weight:600;border-bottom:2px solid #cbd5e1;">${t('fieldsTableHeaderField')}</th><th style="padding:8px 12px;text-align:left;font-weight:600;border-bottom:2px solid #cbd5e1;">${t('fieldsTableHeaderValue')}</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

export function generateNoteDeReglement(
  data: NoteDeReglementData,
  t: Translator,
  locale: string,
): void {
  const today = formatDate(new Date(), locale);
  const summaries = extractSummariesFromLLM(data.llmOutputs);
  const fieldsTable = extractFieldsTable(data.extractedFields, t);

  const tasksHtml = data.tasks.map(t =>
    `<li style="margin-bottom:4px;">${t.done ? '✅' : '⬜'} ${t.task}</li>`
  ).join('');

  const filesHtml = data.files.map(f =>
    `<li style="margin-bottom:2px;">📄 ${f.filename}</li>`
  ).join('');

  const summariesHtml = summaries.length > 0
    ? summaries.map(s => `<li style="margin-bottom:8px;">${s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</li>`).join('')
    : `<li style="color:#94a3b8;font-style:italic;">${t('analysisUnavailable')}</li>`;

  const htmlLang = locale === 'en' ? 'en' : 'fr';

  const html = `<!DOCTYPE html>
<html lang="${htmlLang}">
<head>
  <meta charset="utf-8">
  <title>${t('windowTitle')} — ${data.claimNumber || data.applicationId}</title>
  <style>
    @media print { body { margin: 0; } .no-print { display: none; } }
    body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1e293b; margin: 40px; line-height: 1.6; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid ${brand.primary}; padding-bottom: 16px; margin-bottom: 24px; }
    .logo { font-size: 28px; font-weight: 700; color: ${brand.primary}; }
    .logo small { font-size: 14px; font-weight: 400; color: #475569; display: block; }
    .ref-block { text-align: right; font-size: 13px; color: #475569; }
    .ref-block strong { color: #1e293b; }
    h1 { font-size: 22px; color: ${brand.primary}; margin: 24px 0 8px; border-left: 4px solid ${brand.primary}; padding-left: 12px; }
    h2 { font-size: 16px; color: #334155; margin: 20px 0 8px; }
    .section { margin-bottom: 24px; }
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; font-size: 14px; }
    .info-grid dt { color: #64748b; font-weight: 500; }
    .info-grid dd { margin: 0; font-weight: 600; }
    .settlement-box { background: ${brand.primary}0D; border: 2px solid ${brand.primary}; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center; }
    .settlement-box .amount { font-size: 32px; font-weight: 700; color: ${brand.primary}; }
    .settlement-box .label { font-size: 14px; color: #475569; margin-top: 4px; }
    .footer { margin-top: 40px; padding-top: 16px; border-top: 2px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }
    .stamp { margin-top: 32px; display: flex; justify-content: space-between; font-size: 13px; }
    .stamp-box { border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px 24px; text-align: center; min-width: 200px; }
    .stamp-box .title { font-size: 11px; color: #64748b; margin-bottom: 40px; }
    .stamp-box .line { border-top: 1px solid #1e293b; padding-top: 4px; font-size: 12px; }
    ul { padding-left: 20px; }
    .print-btn { position: fixed; bottom: 24px; right: 24px; background: ${brand.primary}; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .print-btn:hover { background: ${brand.accent}; }
  </style>
</head>
<body>
  <button class="print-btn no-print" onclick="window.print()">${t('printButton')}</button>

  <div class="header">
    <div class="logo">
      ${brand.companyName}<br>
      <small>${t('headerLogoSubtitle', { brandName: brand.name })}</small>
    </div>
    <div class="ref-block">
      <div><strong>${t('claimNumberLabel')}</strong> ${data.claimNumber || data.applicationId}</div>
      <div><strong>${t('policyNumberLabel')}</strong> ${data.policyNumber || '—'}</div>
      <div><strong>${t('dateLabel')}</strong> ${today}</div>
      <div><strong>${t('fileRefLabel')}</strong> ${data.applicationId}</div>
    </div>
  </div>

  <h1>${t('titleH1')}</h1>

  <div class="section">
    <h2>${t('section1')}</h2>
    <dl class="info-grid">
      <dt>${t('insuredName')}</dt><dd>${data.insuredName || '—'}</dd>
      <dt>${t('policyNumber')}</dt><dd>${data.policyNumber || '—'}</dd>
      <dt>${t('propertyAddress')}</dt><dd>${data.propertyAddress || '—'}</dd>
      <dt>${t('lineOfBusiness')}</dt><dd>${data.lineOfBusiness}</dd>
      <dt>${t('claimDate')}</dt><dd>${data.claimDate || '—'}</dd>
      <dt>${t('causeOfLoss')}</dt><dd>${data.causeOfLoss}</dd>
    </dl>
  </div>

  <div class="section">
    <h2>${t('section2')}</h2>
    ${fieldsTable}
  </div>

  <div class="section">
    <h2>${t('section3')}</h2>
    <ul>${summariesHtml}</ul>
  </div>

  <div class="section">
    <h2>${t('section4')}</h2>
    <dl class="info-grid">
      <dt>${t('totalEstimated')}</dt><dd>${data.totalEstimated || '—'}</dd>
      <dt>${t('deductible')}</dt><dd>${data.deductible || '250 €'}</dd>
      <dt>${t('recommendedAmount')}</dt><dd>${data.settlementAmount || '—'}</dd>
    </dl>
    <div class="settlement-box">
      <div class="amount">${data.settlementAmount || data.totalEstimated || '—'}</div>
      <div class="label">${t('settlementBoxLabel')}</div>
    </div>
  </div>

  <div class="section">
    <h2>${t('section5')}</h2>
    <ul>${tasksHtml}</ul>
  </div>

  <div class="section">
    <h2>${t('section6')}</h2>
    <ul>${filesHtml}</ul>
    <p style="font-size:12px;color:#64748b;margin-top:8px;">${t('filesAttached', { count: data.files.length })}</p>
  </div>

  <div class="stamp">
    <div class="stamp-box">
      <div class="title">${t('stampHandler')}</div>
      <div class="line">${t('stampDate', { date: today })}</div>
    </div>
    <div class="stamp-box">
      <div class="title">${t('stampSupervisor')}</div>
      <div class="line">${t('stampDateEmpty')}</div>
    </div>
  </div>

  <div class="footer">
    <p>${t('footerLine1', { brandName: brand.name, companyName: brand.companyName })}</p>
    <p>${t('footerLine2', { companyName: brand.companyName })}</p>
    <p>${t('footerLine3', { companyName: brand.companyName })}</p>
  </div>
</body>
</html>`;

  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
  }
}
