'use client';

import { useState } from 'react';
import clsx from 'clsx';
import { Bot, Shield, FileSearch, BarChart3, Workflow } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ChatMode } from './types';

const MODES = [
  { id: 'auto', labelKey: 'agentAuto', descKey: 'agentAutoDesc', icon: Bot, activeClass: 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300' },
  { id: 'data', labelKey: 'agentData', descKey: 'agentDataDesc', icon: null, activeClass: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300', fabric: true },
  { id: 'policy', labelKey: 'agentPolicy', descKey: 'agentPolicyDesc', icon: Shield, activeClass: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300' },
  { id: 'analysis', labelKey: 'agentAnalysis', descKey: 'agentAnalysisDesc', icon: FileSearch, activeClass: 'bg-violet-100 text-violet-700 ring-1 ring-violet-300' },
  { id: 'dashboard', labelKey: 'agentDashboard', descKey: 'agentDashboardDesc', icon: BarChart3, activeClass: 'bg-cyan-100 text-cyan-700 ring-1 ring-cyan-300' },
  { id: 'workflow', labelKey: 'agentWorkflow', descKey: 'agentWorkflowDesc', icon: Workflow, activeClass: 'bg-fuchsia-100 text-fuchsia-700 ring-1 ring-fuchsia-300' },
] as const;

function FabricGlyph({ active }: { active: boolean }) {
  return (
    <svg className="h-3 w-3" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 1L14.5 5v6L8 15 1.5 11V5L8 1z" fill={active ? '#E8680C' : '#94a3b8'} opacity="0.85" />
      <path d="M8 1L14.5 5 8 9 1.5 5 8 1z" fill={active ? '#F59E0B' : '#cbd5e1'} />
    </svg>
  );
}

function Tooltip({ title, children, align = 'left' }: { title: string; children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <div
      className={clsx(
        'pointer-events-none absolute bottom-full z-50 mb-1.5 min-w-[180px] max-w-[240px] rounded-lg bg-slate-800 px-3 py-2 text-[10px] text-white shadow-lg',
        align === 'left' ? 'left-0' : 'right-0',
      )}
    >
      <div className="mb-0.5 font-semibold">{title}</div>
      <div className="leading-snug text-slate-300">{children}</div>
    </div>
  );
}

interface ChatModeBarProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  /** The Fabric data mode is offered only when the data agent is connected. */
  fabricAvailable: boolean;
  useCorrections: boolean;
  onToggleCorrections: () => void;
}

/** Chat modes (one per specialized agent) and the handler-corrections toggle, on one wrapping row. */
export default function ChatModeBar({
  mode,
  onModeChange,
  fabricAvailable,
  useCorrections,
  onToggleCorrections,
}: ChatModeBarProps) {
  const t = useTranslations('chat');
  const [hovered, setHovered] = useState<string | null>(null);
  const hoverProps = (id: string) => ({
    onMouseEnter: () => setHovered(id),
    onMouseLeave: () => setHovered(null),
    onFocus: () => setHovered(id),
    onBlur: () => setHovered(null),
  });

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1" role="toolbar" aria-label={t('chatModes')}>
      {MODES.filter((item) => !('fabric' in item) || fabricAvailable).map((item) => {
        const isActive = mode === item.id;
        const isFabric = 'fabric' in item;
        const Icon = item.icon;
        return (
          <div key={item.id} className="relative">
            <button
              type="button"
              aria-pressed={isActive}
              onClick={() => onModeChange(item.id)}
              {...hoverProps(item.id)}
              className={clsx(
                'flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-medium transition-all',
                isActive ? item.activeClass : 'bg-slate-100 text-slate-500 hover:bg-slate-200',
              )}
            >
              {isFabric ? <FabricGlyph active={isActive} /> : Icon && <Icon className="h-3 w-3" aria-hidden />}
              {t(item.labelKey)}
              {isFabric && (
                <span
                  className={clsx(
                    'ml-0.5 rounded px-1 py-px text-[8px] font-semibold leading-tight',
                    isActive ? 'bg-orange-200 text-orange-800' : 'bg-slate-200 text-slate-500',
                  )}
                >
                  Fabric
                </span>
              )}
            </button>
            {hovered === item.id && (
              <Tooltip title={t(item.labelKey)}>
                {t(item.descKey)}
                {isFabric && <div className="mt-1 text-[9px] text-orange-300">Microsoft Fabric Data Agent — NL→SQL</div>}
              </Tooltip>
            )}
          </div>
        );
      })}
      <div className="relative ml-auto">
        <button
          type="button"
          aria-pressed={useCorrections}
          aria-label={t('correctionsToggle')}
          onClick={onToggleCorrections}
          {...hoverProps('hitl')}
          className={clsx(
            'flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-medium transition-all',
            useCorrections ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300' : 'bg-slate-100 text-slate-400',
          )}
        >
          <span className={clsx('h-1.5 w-1.5 rounded-full', useCorrections ? 'bg-emerald-500' : 'bg-slate-300')} />
          HITL
        </button>
        {hovered === 'hitl' && (
          <Tooltip title={t('correctionsTitle')} align="right">
            {useCorrections ? t('correctionsOn') : t('correctionsOff')}
          </Tooltip>
        )}
      </div>
    </div>
  );
}
