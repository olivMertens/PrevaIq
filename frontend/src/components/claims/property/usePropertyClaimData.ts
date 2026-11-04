'use client';

import { useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { ApplicationMetadata, ContextTask } from '@/lib/types';
import { getMediaUrl } from '@/lib/api';
import { brand, isWorkbenchSystem } from '@/lib/brand';
import type { GalleryItem } from '../../GalleryLightbox';
import type { StepItem } from '@/components/case/NextSteps';
import {
  DOMMAGES_FIELDS,
  classifyDocument,
  formatParsedFields,
  getFieldLabel,
  getFieldValue,
  getFileTypeInfo,
  parseAmount,
} from './propertyClaimHelpers';

/** Everything the property cockpit derives from the application (moved from the former overview). */
export function usePropertyClaimData(application: ApplicationMetadata | null) {
  const t = useTranslations('claims');
  const locale = useLocale();
  // Stable references: the Client 360 lookup effect and every derived memo depend on them.
  const ef = useMemo(() => application?.extracted_fields || {}, [application?.extracted_fields]);
  const llmOutputs = useMemo(
    () => (application?.llm_outputs || {}) as Record<string, unknown>,
    [application?.llm_outputs],
  );
  const files = useMemo(() => application?.files || [], [application?.files]);
  const docMarkdown = String((application as unknown as Record<string, unknown>)?.document_markdown || '');

  // Customer 360 cross-reference — by external_reference or auto-match by name
  const externalReference = application?.external_reference ?? null;
  const [customerData, setCustomerData] = useState<Record<string, unknown> | null>(null);
  const [autoMatchedId, setAutoMatchedId] = useState<string | null>(null);
  const matchedCustomerId = externalReference || autoMatchedId;
  useEffect(() => {
    if (externalReference) {
      fetch(`/api/customers/${encodeURIComponent(externalReference)}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setCustomerData(data); })
        .catch(() => {});
      return;
    }
    // Auto-match by insured name from extracted fields
    const insuredName = getFieldValue(ef, ['NomAssure', 'AssuréNom', 'NomSouscripteur'], '');
    if (!insuredName) return;
    fetch('/api/customers')
      .then(r => r.ok ? r.json() : [])
      .then((customers: Array<{ id: string; name: string }>) => {
        const nameParts = insuredName.toLowerCase().split(/\s+/);
        const match = customers.find((c: { id: string; name: string }) => {
          const cName = c.name?.toLowerCase() || '';
          return nameParts.some(p => p.length > 2 && cName.includes(p));
        });
        if (match) {
          setAutoMatchedId(match.id);
          fetch(`/api/customers/${encodeURIComponent(match.id)}`)
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data) setCustomerData(data); })
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [externalReference, ef]);

  // Derive key info from document_markdown when structured fields are missing or unusable.
  const markdownDerivedFields = useMemo(() => {
    if (!docMarkdown) return [];
    const fields: { name: string; value: string }[] = [];
    const seen = new Set<string>();

    // Strip HTML tags/entities and collapse whitespace so a value never renders as "</td>".
    const clean = (raw: string): string =>
      raw
        .replace(/<[^>]*>/g, ' ')
        .replace(/&nbsp;|&amp;|&lt;|&gt;|&#\d+;/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    // Map a source label (document wording, FR) to a canonical field key localised via getFieldLabel.
    const canonicalFor = (label: string): string | null => {
      const l = label.toLowerCase();
      if (/(n°|numero|numéro).*(contrat|police)/.test(l)) return 'NumeroContrat';
      if (/(n°|numero|numéro).*(client|sociétaire|societaire|adhérent|adherent)/.test(l)) return 'NumeroSocietaire';
      if (/(nom|prénom|prenom|assuré|assure|souscripteur|conducteur)/.test(l)) return 'NomAssure';
      if (/adresse/.test(l)) return 'AdresseAssure';
      if (/e-?mail|courriel/.test(l)) return 'EmailAssure';
      if (/t[ée]l[ée]?phone|\btél\b|\btel\b/.test(l)) return 'TelephoneAssure';
      if (/date.*(sinistre|incident)/.test(l)) return 'DateSinistre';
      if (/(nature|cause).*(sinistre|dommage)/.test(l)) return 'NatureSinistre';
      if (/franchise/.test(l)) return 'FranchiseApplicable';
      if (/(montant|total|estimation|estim[ée])/.test(l)) return 'MontantEstime';
      return null;
    };

    const pushField = (canonical: string, rawValue: string) => {
      const value = clean(rawValue);
      if (!value || value.length < 2 || /[<>]/.test(value)) return; // empty / fragment / residual markup
      if (seen.has(canonical)) return;
      seen.add(canonical);
      fields.push({ name: getFieldLabel(canonical, t), value: value.slice(0, 120) });
    };

    // 1) Preferred: parse HTML tables from Content Understanding (prebuilt-layout) output.
    //    Rows are <tr><td>N° de contrat :</td><td>HAB-33-…</td></tr> — label and value sit
    //    in separate cells, which the previous single-line regex could not read (it captured "</td>").
    const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let rowMatch: RegExpExecArray | null;
    while ((rowMatch = rowRe.exec(docMarkdown)) !== null) {
      const cells = Array.from(rowMatch[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)).map((m) => m[1]);
      if (cells.length < 2) continue;
      const canonical = canonicalFor(clean(cells[0]));
      if (canonical) pushField(canonical, cells[1]);
    }

    // 2) Fallback: plain-text "Label : value" lines (non-HTML markdown). Capture stops at
    //    the first "<" so a leaked tag can never become the value.
    if (fields.length === 0) {
      const patterns: [RegExp, string][] = [
        [/(?:numéro|n°)\s*(?:de\s*)?(?:contrat|police)\s*[:：]\s*([^\n<]+)/i, 'NumeroContrat'],
        [/(?:nom|assuré|souscripteur)\s*[:：]\s*([^\n<]+)/i, 'NomAssure'],
        [/adresse\s*[:：]\s*([^\n<]+)/i, 'AdresseAssure'],
        [/(?:date)\s*(?:du\s*)?(?:sinistre|incident)\s*[:：]\s*([^\n<]+)/i, 'DateSinistre'],
        [/(?:nature|cause)\s*(?:du\s*)?(?:sinistre|dommage)\s*[:：]\s*([^\n<]+)/i, 'NatureSinistre'],
        [/(?:montant|total|estimation)\s*[:：]\s*([^\n<]+)/i, 'MontantEstime'],
        [/franchise\s*[:：]\s*([^\n<]+)/i, 'FranchiseApplicable'],
      ];
      for (const [regex, canonical] of patterns) {
        const m = docMarkdown.match(regex);
        if (m) pushField(canonical, m[1]);
      }
    }

    // 3) Enrich with Customer 360 profile when available.
    if (customerData) {
      const profile = (customerData as Record<string, unknown>).profile as Record<string, unknown> | undefined;
      if (profile?.name) pushField('NomAssure', String(profile.name));
      if (profile?.email) pushField('EmailAssure', String(profile.email));
      if (profile?.phone) pushField('TelephoneAssure', String(profile.phone));
    }

    return fields;
  }, [docMarkdown, customerData, t]);

  // Derive damages from document_markdown or LLM outputs
  const markdownDerivedDamages = useMemo(() => {
    const items: { description: string; related: string }[] = [];
    const seen = new Set<string>();

    // Normalize a candidate damage phrase; return null when it is junk/a fragment.
    const sanitize = (raw: string): string | null => {
      const s = raw
        .replace(/<[^>]*>/g, ' ') // strip any leaked HTML tags (e.g. </td>)
        .replace(/[*_`#>]+/g, ' ') // strip markdown emphasis / heading / quote marks
        .replace(/&nbsp;|&amp;|&lt;|&gt;/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (s.length < 12) return null; // too short → fragment
      if (!/^[A-Za-zÀ-ÖØ-öø-ÿ0-9]/.test(s)) return null; // must start with a letter/digit (rejects "s, …", ", …")
      if (/[<>]/.test(s)) return null; // residual HTML → reject
      return s.slice(0, 180);
    };

    const add = (raw: string) => {
      if (items.length >= 6) return;
      const c = sanitize(raw);
      if (!c) return;
      const key = c.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      items.push({ description: c, related: t('formatLabels.oui') });
    };

    // 1) Preferred: structured LLM damage_assessment.damage_areas (clean path)
    const damageSection = llmOutputs.damage_assessment as Record<string, unknown> | undefined;
    if (damageSection) {
      for (const [, val] of Object.entries(damageSection)) {
        const sub = val as { parsed?: { damage_areas?: Array<{ location?: string; severity?: string; description?: string }> } } | undefined;
        const areas = sub?.parsed?.damage_areas;
        if (Array.isArray(areas)) {
          for (const area of areas) {
            const head = [area.location, area.description].filter(Boolean).join(' — ');
            const sev = area.severity ? ` (${area.severity})` : '';
            add(`${head}${sev}`);
          }
        }
      }
    }

    // 2) Fallback: derive from document markdown only when no structured areas exist.
    if (items.length === 0 && docMarkdown) {
      const text = docMarkdown.replace(/<[^>]*>/g, ' '); // strip HTML before scanning
      // 2a) Explicit "Dégâts/Dommages constatés : …" labels (value to end of line only)
      const labelPatterns = [
        /(?:dégâts?\s*(?:des\s*eaux?|constatés?))\s*[:：]\s*([^\n\r]+)/gi,
        /(?:dommages?\s*(?:constatés?|visibles?|apparents?))\s*[:：]\s*([^\n\r]+)/gi,
      ];
      for (const re of labelPatterns) {
        let m: RegExpExecArray | null;
        while ((m = re.exec(text)) !== null && items.length < 6) add(m[1]);
      }
      // 2b) Structured photo-analysis bullets: "- **<label>** : <value>" — take the
      // full value of damage-relevant labels instead of matching keyword stems mid-word.
      if (items.length === 0) {
        const bulletRe = /^[\s>*-]*\*\*([^*]+?)\*\*\s*[:：]\s*([^\n\r]+)$/gim;
        let b: RegExpExecArray | null;
        while ((b = bulletRe.exec(docMarkdown)) !== null && items.length < 6) {
          if (/(nature du sinistre|étendue des dommages|éléments?\s+affect|zone affect|dégât|dommage)/i.test(b[1])) {
            add(b[2]);
          }
        }
      }
    }
    return items;
  }, [llmOutputs, docMarkdown, t]);

  // Build AI summary from LLM outputs
  const aiSummary = useMemo(() => {
    const parts: string[] = [];
    for (const [, subsections] of Object.entries(llmOutputs)) {
      if (subsections && typeof subsections === 'object') {
        for (const [, val] of Object.entries(subsections as Record<string, unknown>)) {
          const sub = val as { parsed?: Record<string, unknown>; raw?: string } | undefined;
          if (sub?.parsed) {
            // Check for summary field first
            if (typeof sub.parsed.summary === 'string' && sub.parsed.summary) {
              parts.push(sub.parsed.summary);
            }
            // Fallback: check for _error (analysis ran but parsing failed)
            else if (typeof sub.parsed._error === 'string') {
              // Skip error entries — don't add them to summary
            }
            // Fallback: format parsed JSON into readable text
            else {
              const lines = formatParsedFields(sub.parsed, '', t, locale);
              if (lines.length > 0) {
                parts.push(lines.join('\n'));
              }
            }
          }
        }
      }
    }
    // If llm_outputs has content but no extractable summaries, show generic
    if (parts.length === 0 && Object.keys(llmOutputs).length > 0) {
      const sectionCount = Object.keys(llmOutputs).length;
      parts.push(t('analysisDialog.analysisComplete', { count: sectionCount }));
    }
    return parts.join('\n\n');
  }, [llmOutputs, locale, t]);

  // Amount comparison: customer claimed vs AI-assessed
  const amountComparison = useMemo(() => {
    // Customer's declared/claimed amount from extracted fields
    const claimed = parseAmount(getFieldValue(ef, ['MontantEstime', 'MontantTotal', 'TotalIncurred'], ''));

    // AI-recommended indemnity from LLM payout_calculation
    let recommended = NaN;
    const payoutSection = llmOutputs.payout_calculation as Record<string, unknown> | undefined;
    if (payoutSection) {
      for (const val of Object.values(payoutSection)) {
        const sub = val as { parsed?: Record<string, unknown> } | undefined;
        const p = sub?.parsed;
        if (p) {
          const r = Number(p.montant_indemnisation_recommande || p.montant_indemnisation || p.recommended_payout || 0);
          if (r > 0) { recommended = r; break; }
          const rep = Number(p.montant_estime_reparations || p.total_estimated_cost || 0);
          if (rep > 0 && isNaN(recommended)) { recommended = rep; }
        }
      }
    }

    if (isNaN(claimed) || claimed === 0) return null;
    if (isNaN(recommended) || recommended === 0) return null;

    const delta = claimed - recommended;
    const pctDelta = ((delta / recommended) * 100);
    return { claimed, recommended, delta, pctDelta, hasOverclaim: delta > 0 && pctDelta > 5 };
  }, [ef, llmOutputs]);

  // Build evidence items from actual uploaded files + policy reference PDFs
  const evidenceItems = useMemo(() => {
    const items = files.map(f => {
      const classification = classifyDocument(f.filename, t);
      const fileType = getFileTypeInfo(f.filename, t);
      return {
        source: f.filename,
        type: classification.type,
        summary: classification.summary,
        supports: true,
        challenges: false,
        fileType,
        isPolicyRef: false,
        policyId: undefined as 'habitation' | 'sante' | undefined,
      };
    });
    // Add policy PDFs as reference docs
    items.push({
      source: t('evidence.cgHabitation'),
      type: 'Police',
      summary: t('evidence.cgHabitationDesc'),
      supports: true,
      challenges: false,
      fileType: { label: 'PDF', icon: 'pdf' as const },
      isPolicyRef: true,
      policyId: 'habitation',
    });
    items.push({
      source: t('evidence.cgSante'),
      type: 'Police',
      summary: t('evidence.cgSanteDesc'),
      supports: true,
      challenges: false,
      fileType: { label: 'PDF', icon: 'pdf' as const },
      isPolicyRef: true,
      policyId: 'sante',
    });
    return items;
  }, [files, t]);

  // Build coherent narrative timeline from extracted fields (correlates with ChronologicalOverview)
  const liabilityEvents = useMemo(() => {
    if (files.length === 0) return [{ date: '—', type: t('timeline.waiting'), desc: t('timeline.waitingDescription'), impact: 'neutral' }];

    const createdDate = application?.created_at ? new Date(application.created_at) : new Date();
    const fmtDate = (d: Date) => new Intl.DateTimeFormat(locale).format(d);

    // Try to build from extracted fields first
    const dateSinistre = getFieldValue(ef, ['DateSinistre']);
    const natureSinistre = getFieldValue(ef, ['NatureSinistre']);
    const description = getFieldValue(ef, ['DescriptionSinistre']);
    const lieu = getFieldValue(ef, ['LieuSinistre']);
    const montant = getFieldValue(ef, ['MontantEstime']);
    const mesures = getFieldValue(ef, ['MesuresConservatoires']);
    const nomAssure = getFieldValue(ef, ['NomAssure', 'AssuréNom']);
    const contrat = getFieldValue(ef, ['NumeroContrat']);

    // Parse incident date
    let incidentDate: Date | null = null;
    if (dateSinistre) {
      const parts = dateSinistre.match(/(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})/);
      if (parts) incidentDate = new Date(Number(parts[3].length === 2 ? '20' + parts[3] : parts[3]), Number(parts[2]) - 1, Number(parts[1]));
    }

    // If we have extracted fields, build narrative events
    if (incidentDate && natureSinistre) {
      const events: { date: string; type: string; desc: string; impact: string; sort: number }[] = [];
      const dayAfter = new Date(incidentDate.getTime() + 86400000);
      const twoDaysAfter = new Date(incidentDate.getTime() + 2 * 86400000);

      events.push({ date: fmtDate(incidentDate), type: t('timeline.incident', { nature: natureSinistre }), desc: lieu ? t('timeline.incidentLocation', { location: lieu }) : t('timeline.incidentNoLocation'), impact: 'disputes', sort: incidentDate.getTime() });

      if (description) {
        events.push({ date: fmtDate(dayAfter), type: t('timeline.damage'), desc: nomAssure ? t('timeline.damageDesc', { name: nomAssure }) : t('timeline.damageDescDefault'), impact: 'neutral', sort: dayAfter.getTime() });
      }

      if (mesures) {
        events.push({ date: fmtDate(dayAfter), type: t('timeline.conservatory'), desc: t('timeline.conservatoryDesc'), impact: 'supports', sort: dayAfter.getTime() + 1 });
      }

      events.push({ date: fmtDate(twoDaysAfter), type: t('timeline.declaration'), desc: contrat ? t('timeline.declarationDesc', { contract: contrat }) : t('timeline.declarationDescNoContract'), impact: 'supports', sort: twoDaysAfter.getTime() });

      if (montant) {
        const formatted = !isNaN(Number(montant))
          ? new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(Number(montant))
          : montant;
        events.push({ date: fmtDate(twoDaysAfter), type: t('timeline.estimation', { amount: formatted }), desc: t('timeline.estimationDesc'), impact: 'neutral', sort: twoDaysAfter.getTime() + 1 });
      }

      events.push({ date: fmtDate(createdDate), type: t('timeline.reception'), desc: t('timeline.receptionDesc'), impact: 'supports', sort: createdDate.getTime() });

      // Dated from the real analysis completion, and only once an analysis exists.
      const analysedAt = application?.orchestration?.stages?.analysis?.completed_at;
      if (analysedAt || Object.keys(llmOutputs).length > 0) {
        const analysisDate = analysedAt ? new Date(analysedAt) : createdDate;
        events.push({ date: fmtDate(analysisDate), type: t('timeline.analysisComplete'), desc: t('timeline.analysisCompleteDesc', { count: files.length }), impact: 'supports', sort: analysisDate.getTime() + 1 });
      }

      // Merge persisted action_history (actions + decisions)
      if (application?.action_history) {
        for (const action of application.action_history) {
          const actionDate = new Date(action.at);

          // Decision entries — rich rendering with icon and justification
          if ((action as Record<string, unknown>).decision) {
            const dec = action as Record<string, unknown>;
            const decisionIcons: Record<string, string> = {
              approve: '✅', approve_with_conditions: '⚠️', defer: '⏳', decline: '❌',
            };
            const icon = decisionIcons[String(dec.decision)] || '📋';
            let desc = dec.notes ? String(dec.notes) : action.source || brand.name;
            if (dec.ai_recommendation) {
              desc += ` — ${t('timeline.aiRecommendation')}: ${dec.ai_recommendation}`;
            }
            if (dec.validation_divergence && dec.validation_divergence !== 'aligned') {
              desc += ` ⚡ ${t('timeline.aiHumanDivergence')}`;
            }
            if (dec.conditions) {
              desc += ` | ${t('timeline.conditions')}: ${dec.conditions}`;
            }
            events.push({
              date: fmtDate(actionDate),
              type: `${icon} ${action.label}`,
              desc,
              impact: dec.decision === 'decline' ? 'disputes' : 'supports',
              sort: actionDate.getTime(),
            });
            continue;
          }

          // Generic action_history entries
          const systems = (action.systems || []).filter((s: string) => s && !isWorkbenchSystem(s));
          const uniqueSystems = [...new Set(systems)];
          const badges = uniqueSystems.map((s: string) => {
            if (s === 'SIU') return '🔍 SIU';
            if (s === 'GED') return '📂 GED';
            if (s === 'Email') return '✉️ Email';
            return s;
          }).join(' · ');
          events.push({
            date: fmtDate(actionDate),
            type: action.label,
            desc: badges ? t('timeline.systems', { systems: badges }) : action.source,
            impact: action.performed === 'HITL' ? 'disputes' : 'supports',
            sort: actionDate.getTime(),
          });
        }
      }

      // Fallback: synthesize timeline entry from llm_outputs.decision for existing dossiers
      // that have a decision but no action_history entry for it
      const decisionData = (llmOutputs as Record<string, unknown>).decision as Record<string, unknown> | undefined;
      const hasDecisionInHistory = application?.action_history?.some(
        (a: Record<string, unknown>) => !!(a as Record<string, unknown>).decision
      );
      if (decisionData && !hasDecisionInHistory) {
        const decIcons: Record<string, string> = {
          approve: '✅', approve_with_conditions: '⚠️', defer: '⏳', decline: '❌',
        };
        const decStr = String(decisionData.decision || '');
        const icon = decIcons[decStr] || '📋';
        const label = ['approve', 'approve_with_conditions', 'defer', 'decline'].includes(decStr)
          ? t(`timeline.decisions.${decStr}`)
          : t('timeline.decision', { decision: decStr });
        const decidedAt = decisionData.decided_at
          ? new Date(typeof decisionData.decided_at === 'number' ? decisionData.decided_at * 1000 : String(decisionData.decided_at))
          : new Date();
        events.push({
          date: fmtDate(decidedAt),
          type: `${icon} ${label}`,
          desc: decisionData.notes ? String(decisionData.notes) : t('timeline.decisionSaved'),
          impact: decStr === 'decline' ? 'disputes' : 'supports',
          sort: decidedAt.getTime(),
        });
      }

      events.sort((a, b) => a.sort - b.sort);
      return events;
    }

    // Fallback: simple file-based timeline
    return files.map(f => {
      const classification = classifyDocument(f.filename, t);
      return { date: fmtDate(createdDate), type: classification.type, desc: f.filename, impact: 'supports' };
    });
  }, [files, application, ef, llmOutputs, locale, t]);

  // Build damage items from extracted fields — only damage-related fields with French labels
  const injuries = useMemo(() => {
    const items: { diagnosis: string; related: string }[] = [];
    for (const [key, val] of Object.entries(ef)) {
      const fieldVal = val as { field_name?: string; value?: unknown } | undefined;
      if (!fieldVal || fieldVal.value == null || fieldVal.value === '') continue;
      const rawName = fieldVal.field_name || key.split(':').pop() || key;
      // Only include damage-related fields
      if (!DOMMAGES_FIELDS.has(rawName)) continue;
      const label = getFieldLabel(rawName, t);
      items.push({ diagnosis: `${label}: ${fieldVal.value}`, related: t('formatLabels.oui') });
    }
    return items.slice(0, 10);
  }, [ef, t]);

  // Build gallery items for lightbox (all files with URLs + policy PDFs)
  const applicationId = application?.id;
  const galleryItems: GalleryItem[] = useMemo(() => {
    if (!applicationId) return [];
    return evidenceItems.map(item => {
      if (item.policyId) {
        return {
          url: getMediaUrl(`/api/policy-pdfs/${item.policyId}`),
          filename: item.source,
          type: 'pdf' as const,
          label: item.type,
        };
      }
      return {
        url: getMediaUrl(`/api/applications/${applicationId}/files/${encodeURIComponent(item.source)}`),
        filename: item.source,
        type: item.fileType.icon as GalleryItem['type'],
        label: item.type,
      };
    });
  }, [evidenceItems, applicationId]);

  // Backend context tasks carry a key and a priority; fall back to the basic checklist.
  const steps: StepItem[] = useMemo(() => {
    const backendTasks: ContextTask[] = application?.context_tasks || [];
    if (backendTasks.length > 0) {
      return backendTasks.map((task) => ({
        key: task.key,
        task: task.task,
        priority: task.priority,
        dueOffsetDays: task.due_offset_days,
      }));
    }
    return [
      { key: 'verify_coverage', task: t('tasks.verifyCoverage'), priority: 'high', dueOffsetDays: 0 },
      { key: 'mandate_expert', task: t('tasks.mandateExpert'), priority: 'high', dueOffsetDays: 1 },
      { key: 'apply_franchise', task: t('tasks.applyFranchise'), priority: 'medium', dueOffsetDays: 3 },
    ];
  }, [application?.context_tasks, t]);

  return {
    ef,
    llmOutputs,
    files,
    docMarkdown,
    customerData,
    matchedCustomerId,
    markdownDerivedFields,
    markdownDerivedDamages,
    aiSummary,
    amountComparison,
    evidenceItems,
    liabilityEvents,
    injuries,
    galleryItems,
    steps,
  };
}
