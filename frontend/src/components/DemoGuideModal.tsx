'use client';

import BrandMark from './BrandMark';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { HelpCircle, X, ChevronDown, ChevronRight, Upload, MessageSquare, CheckCircle, Search, CloudRain, FileText, ClipboardList, Car, Home, Shield, Users, Stethoscope } from 'lucide-react';
import clsx from 'clsx';
import { brand } from '@/lib/brand';

interface Step {
  icon: typeof Upload;
}

interface Scenario {
  id: string;
  icon: typeof CloudRain;
  color: string;
  demoPdf: string;
  steps: Step[];
}

interface ScenarioContent {
  label: string;
  summary: string;
  emptyDemo: string;
  steps: Array<{ title: string; detail: string; tip?: string }>;
}

const DEMO_DIR = brand.demoAssetsDir;

const SCENARIOS: Scenario[] = [
  {
    id: "habitation",
    icon: CloudRain,
    color: "#2563eb",
    demoPdf: `${DEMO_DIR}/property-claims/wine-cellar/declaration-sinistre-habitation.pdf`,
    steps: [
      { icon: CloudRain },
      { icon: Upload },
      { icon: FileText },
      { icon: Shield },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
  {
    id: "auto",
    icon: Car,
    color: "#dc2626",
    demoPdf: `${DEMO_DIR}/automotive-claims/parking-impact/thread2-01-client-accident-auto.pdf`,
    steps: [
      { icon: Car },
      { icon: Upload },
      { icon: FileText },
      { icon: Search },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
  {
    id: "sante",
    icon: ClipboardList,
    color: brand.primary,
    demoPdf: `${DEMO_DIR}/health-underwriting/souscription-sante-lefevre.pdf`,
    steps: [
      { icon: ClipboardList },
      { icon: Upload },
      { icon: FileText },
      { icon: Search },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
  {
    id: "sante-sinistre",
    icon: Stethoscope,
    color: "#059669",
    demoPdf: `${DEMO_DIR}/health-claims/dental/`,
    steps: [
      { icon: Stethoscope },
      { icon: Upload },
      { icon: FileText },
      { icon: Search },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
  {
    id: "hypothecaire",
    icon: Home,
    color: "#059669",
    demoPdf: `${DEMO_DIR}/mortgage-underwriting/primo-accedant/app-mtg-004/`,
    steps: [
      { icon: Home },
      { icon: Upload },
      { icon: FileText },
      { icon: Search },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
  {
    id: "client360",
    icon: Users,
    color: "#0ea5e9",
    demoPdf: ``,
    steps: [
      { icon: Users },
      { icon: Search },
      { icon: FileText },
      { icon: ClipboardList },
      { icon: MessageSquare },
      { icon: CheckCircle },
    ],
  },
];

export default function DemoGuideModal() {
  const t = useTranslations('demoGuide');
  const [isOpen, setIsOpen] = useState(false);
  const [expandedStep, setExpandedStep] = useState<number | null>(0);
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const scenario = SCENARIOS[scenarioIdx];
  const scenarioContent = t.raw(`scenarios.${scenario.id}`) as ScenarioContent;

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg transition-colors"
        style={{ color: brand.primary, backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` }}
        title={t('openTitle')}
        aria-label={t('openTitle')}
      >
        <HelpCircle className="w-4 h-4" aria-hidden />
        <span className="hidden 2xl:inline">{t('openBadge')}</span>
      </button>
    );
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 z-50" onClick={() => setIsOpen(false)} />

      {/* Modal */}
      <div className="fixed top-1/2 left-1/2 z-50 flex max-h-[92vh] w-[96vw] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4 border-b border-slate-200 rounded-t-2xl"
          style={{ background: `linear-gradient(90deg, ${brand.gradientStart}, ${brand.gradientEnd})` }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 shadow-sm">
              <img src={brand.favicon} alt="" className="h-9 w-9 rounded-lg" />
              <span className="text-sm font-bold tracking-tight" style={{ color: brand.primary }}>
                {brand.name}
              </span>
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-white">
                {t('title')}
              </h2>
              <p className="truncate text-sm font-medium text-white">
                {t('subtitle', { company: brand.companyName, scenario: scenarioContent.label })}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 text-white/70 hover:text-white rounded-lg hover:bg-white/15"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scenario Tabs */}
        <div className="flex flex-wrap gap-1.5 border-b border-slate-200 bg-slate-50/50 px-4 pt-3">
          {SCENARIOS.map((s, i) => {
            const Icon = s.icon;
            const active = scenarioIdx === i;
            const content = t.raw(`scenarios.${s.id}`) as ScenarioContent;
            return (
              <button
                key={s.id}
                onClick={() => { setScenarioIdx(i); setExpandedStep(0); }}
                className={clsx(
                  'flex items-center gap-2 rounded-t-xl border-b-2 px-4 py-3 text-sm font-semibold whitespace-nowrap transition-colors',
                  active
                    ? 'bg-white border-current shadow-sm'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-white/60'
                )}
                style={active ? { color: s.color } : {}}
              >
                <Icon className="h-[18px] w-[18px]" />
                {content.label}
              </button>
            );
          })}
        </div>

        {/* Scenario summary */}
        <div className="px-6 py-3 bg-amber-50 border-b border-amber-100 text-sm">
          <p className="font-medium text-amber-800">
            {t('scenarioLabel')}
          </p>
          <p className="text-amber-700">
            {scenarioContent.summary}
          </p>
        </div>

        {/* Steps */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {scenario.steps.map((step, i) => {
            const isExpanded = expandedStep === i;
            const Icon = step.icon;
            const content = scenarioContent.steps[i];
            return (
              <div key={i} className="border border-slate-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedStep(isExpanded ? null : i)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
                    isExpanded ? '' : 'bg-white hover:bg-slate-50'
                  )}
                  style={isExpanded ? { backgroundColor: `${brand.primary}0D` } : undefined}
                >
                  <Icon
                    className={clsx('w-5 h-5 flex-shrink-0', isExpanded ? '' : 'text-slate-400')}
                    style={isExpanded ? { color: brand.primary } : undefined}
                  />
                  <span
                    className={clsx('text-sm font-medium flex-1', isExpanded ? '' : 'text-slate-700')}
                    style={isExpanded ? { color: brand.primary } : undefined}
                  >
                    {content.title}
                  </span>
                  {isExpanded
                    ? <ChevronDown className="w-4 h-4" style={{ color: brand.secondary }} />
                    : <ChevronRight className="w-4 h-4 text-slate-400" />}
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 pt-1" style={{ backgroundColor: `${brand.primary}08` }}>
                    <p className="text-sm text-slate-600 whitespace-pre-line">
                      {content.detail}
                    </p>
                    {content.tip && (
                      <p className="mt-2 text-xs text-amber-700 bg-amber-50 px-3 py-2 rounded-lg border border-amber-100">
                        💡 {content.tip}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex min-h-[88px] items-center justify-between gap-5 rounded-b-2xl border-t border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex flex-shrink-0 items-center gap-3">
            <div className="flex h-14 items-center rounded-xl bg-white px-4 shadow-sm ring-1 ring-slate-200">
              <img src="/microsoft-logo-gray.avif" alt="Microsoft" className="h-10 w-auto opacity-100" />
            </div>
            <span className="text-lg font-bold text-slate-700">×</span>
            <div className="flex h-14 items-center rounded-xl bg-white px-4 shadow-sm ring-1 ring-slate-200">
              <BrandMark />
            </div>
          </div>
          <p className="hidden flex-1 text-center text-xs font-medium text-slate-700 sm:block">
            {scenario.demoPdf
              ? t('fileLabel', { path: scenario.demoPdf })
              : t('demoLabel', { name: scenarioContent.emptyDemo })}
          </p>
          <button
            onClick={() => setIsOpen(false)}
            className="flex-shrink-0 rounded-lg px-5 py-2.5 text-sm font-semibold text-white"
            style={{ backgroundColor: brand.primary }}
          >
            {t('close')}
          </button>
        </div>
      </div>
    </>
  );
}
