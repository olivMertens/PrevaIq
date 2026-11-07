'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Mail, MessageSquare, FileText, Copy, Check, X, Loader2, Sparkles, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import { useLocale, useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';

interface CommunicationGeneratorProps {
  /** Application ID for API call */
  applicationId: string;
  /** Insured person name */
  insuredName: string;
  /** Claim/case reference */
  claimReference: string;
  /** Current decision status */
  decisionStatus?: 'approved' | 'pending' | 'denied' | 'investigation' | null;
  /** Settlement amount if approved */
  settlementAmount?: string;
  /**
   * Initial tone selection. When omitted, defaults to 'standard'. Callers can
   * pass 'empathetic' when client sentiment is stressed/critical so the UI
   * reflects the recommended tone before the agent clicks Generate.
   */
  defaultTone?: 'empathetic' | 'standard' | 'formal';
}

type CommType = 'email' | 'sms' | 'letter';
type CommTone = 'empathetic' | 'standard' | 'formal';

interface GeneratedComm {
  type: CommType;
  tone: CommTone;
  subject?: string;
  body: string;
  timestamp: string;
}

const COMM_TYPES: { id: CommType; icon: typeof Mail }[] = [
  { id: 'email', icon: Mail },
  { id: 'sms', icon: MessageSquare },
  { id: 'letter', icon: FileText },
];

const TONE_OPTIONS: CommTone[] = ['empathetic', 'standard', 'formal'];

export default function CommunicationGenerator(props: CommunicationGeneratorProps) {
  const locale = useLocale();
  return <CommunicationComposer key={`${props.applicationId}-${locale}`} {...props} />;
}

function CommunicationComposer({
  applicationId,
  insuredName,
  claimReference,
  decisionStatus,
  settlementAmount,
  defaultTone = 'standard',
}: CommunicationGeneratorProps) {
  const tComm = useTranslations('communicationActions');
  const t = useTranslations('communicationGenerator');
  const locale = useLocale();
  const [commType, setCommType] = useState<CommType>('email');
  const [tone, setTone] = useState<CommTone>(defaultTone);
  const [generated, setGenerated] = useState<GeneratedComm | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showToneOptions, setShowToneOptions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      pending.current?.abort();
      pending.current = null;
    };
  }, []);

  const handleGenerate = useCallback(async () => {
    const controller = new AbortController();
    pending.current?.abort();
    pending.current = controller;
    setIsGenerating(true);
    setError(null);
    try {
      const response = await fetch(`/api/applications/${applicationId}/generate-communication`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel: commType, tone, language: locale }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`API error: ${response.status}`);
      const result = await response.json();
      if (typeof result.body !== 'string' || !result.body.trim()) throw new Error('Empty communication response');

      setGenerated({
        type: commType,
        tone,
        subject: result.subject || undefined,
        body: result.body || '',
        timestamp: result.generated_at || new Date().toISOString(),
      });
    } catch (err) {
      if (controller.signal.aborted) return;
      console.error('[CommunicationGenerator] Generation failed:', err);
      setError(t('templateFallback'));
      const status = decisionStatus === 'approved' || decisionStatus === 'denied' ? decisionStatus : 'pending';
      const values = {
        name: insuredName || t('defaultClient'),
        ref: claimReference || applicationId.slice(0, 8),
        amount: settlementAmount || '—',
        brand: brand.companyName,
        phone: brand.insurerPhone,
      };
      const body = t(`templates.${status}.${commType}.body`, values);
      const subject = commType === 'sms'
        ? undefined
        : t(`templates.${status}.${commType}.subject`, values);
      setGenerated({ type: commType, tone, subject, body, timestamp: new Date().toISOString() });
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setIsGenerating(false);
      }
    }
  }, [commType, tone, applicationId, decisionStatus, insuredName, claimReference, settlementAmount, locale, t]);

  const handleCopy = useCallback(async () => {
    if (!generated) return;
    const text = generated.subject ? `${t('subject')}: ${generated.subject}\n\n${generated.body}` : generated.body;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(t('copyError'));
    }
  }, [generated, t]);

  return (
    <div className="space-y-3">
      {error && <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">{error}</p>}
      {/* Type selector */}
      <div className="flex flex-wrap items-center gap-2">
        {COMM_TYPES.map((ct) => {
          const Icon = ct.icon;
          return (
            <button
              key={ct.id}
              type="button"
              disabled={isGenerating}
              aria-pressed={commType === ct.id}
              onClick={() => { setCommType(ct.id); setGenerated(null); }}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all border disabled:opacity-50',
                commType === ct.id
                  ? ''
                  : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'
              )}
              style={commType === ct.id ? {
                color: brand.ink,
                borderColor: `${brand.primary}33`,
                backgroundColor: `${brand.primary}0D`,
              } : undefined}
            >
              <Icon className="w-3.5 h-3.5" />
              {t(`types.${ct.id}`)}
            </button>
          );
        })}
        {/* Tone dropdown */}
        <div className="relative ml-auto">
          <button
            type="button"
            disabled={isGenerating}
            aria-expanded={showToneOptions}
            onClick={() => setShowToneOptions(!showToneOptions)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 hover:text-slate-700 border border-slate-200 rounded-lg bg-white disabled:opacity-50"
          >
            {t('toneLabel')}: {t(`tones.${tone}.label`)}
            <ChevronDown className="w-3 h-3" />
          </button>
          {showToneOptions && (
            <div className="absolute right-0 top-full mt-1 z-10 w-48 bg-white rounded-lg shadow-lg border border-slate-200 py-1">
              {TONE_OPTIONS.map((toneOption) => (
                <button
                  key={toneOption}
                  type="button"
                  disabled={isGenerating}
                  onClick={() => { setTone(toneOption); setShowToneOptions(false); setGenerated(null); }}
                  className={clsx(
                    'w-full text-left px-3 py-2 text-sm hover:bg-slate-50',
                    tone === toneOption ? '' : 'text-slate-600'
                  )}
                  style={tone === toneOption ? { color: brand.ink, backgroundColor: `${brand.primary}0D` } : undefined}
                >
                  <div className="font-medium">{t(`tones.${toneOption}.label`)}</div>
                  <div className="text-xs text-slate-500">{t(`tones.${toneOption}.description`)}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Generate or display */}
      {!generated ? (
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          style={{ backgroundColor: brand.primary }}
        >
          {isGenerating ? (
            <><Loader2 className="w-4 h-4 animate-spin" />{t('generating')}</>
          ) : (
            <><Sparkles className="w-4 h-4" />{t('generate', { type: t(`types.${commType}`) })}</>
          )}
        </button>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5" style={{ color: brand.ink }} />
            <span className="text-sm font-medium text-slate-700">
              {t('generated', { type: t(`types.${generated.type}`) })}
            </span>
            <span className="text-xs text-slate-500">({t(`tones.${generated.tone}.label`)})</span>
            <div className="ml-auto flex items-center gap-1">
              <button onClick={handleCopy} title={tComm('copy')}
                className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
              <button onClick={() => setGenerated(null)} title={tComm('close')}
                className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          {/* Subject (email/letter only) */}
          {generated.subject !== undefined && (
            <div className="px-3 py-1.5 border-b border-slate-100 text-xs">
              <label className="block text-slate-500">{t('subject')}
                <input value={generated.subject} onChange={(event) => setGenerated((current) => current && ({ ...current, subject: event.target.value }))}
                  className="mt-1 w-full rounded border border-slate-200 bg-white p-2 text-sm text-slate-900" />
              </label>
            </div>
          )}
          {/* Body */}
          <textarea aria-label={t('draftBody')} value={generated.body} lang={locale}
            rows={generated.type === 'sms' ? 3 : 12}
            onChange={(event) => setGenerated((current) => current && ({ ...current, body: event.target.value }))}
            className={clsx(
              'block w-full resize-y bg-white p-3 text-sm leading-relaxed text-slate-800 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500',
              generated.type === 'sms' ? 'min-h-28' : 'min-h-64',
            )} />
          {/* Footer actions */}
          <div className="px-3 py-2 bg-slate-50 border-t border-slate-100 flex items-center gap-2">
            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded transition-colors disabled:opacity-50"
              style={{
                color: brand.ink,
                borderColor: `${brand.primary}33`,
                backgroundColor: `${brand.primary}0D`,
              }}
            >
              {isGenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {isGenerating ? t('generating') : t('regenerate')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
