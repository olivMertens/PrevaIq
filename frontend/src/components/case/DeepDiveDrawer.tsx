'use client';

import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import type { DeepDiveTab } from './caseSignals';

export interface DeepDiveTabDef {
  id: DeepDiveTab;
  label: string;
}

interface DeepDiveDrawerProps {
  open: boolean;
  tabs: DeepDiveTabDef[];
  activeTab: DeepDiveTab;
  title: string;
  /** Where the user came from, e.g. the signal that opened the drawer. */
  context?: string;
  onTabChange: (tab: DeepDiveTab) => void;
  onClose: () => void;
  children: React.ReactNode;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/** Side panel for the evidence behind any cockpit fact; keyboard and screen-reader friendly. */
export default function DeepDiveDrawer({ open, tabs, activeTab, title, context, onTabChange, onClose, children }: DeepDiveDrawerProps) {
  const t = useTranslations('caseCockpit.drawer');
  const panelRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const titleId = useId();
  const baseId = useId();

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    tabRefs.current[activeTab]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null,
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
    // Focus moves only when the drawer opens, not on every tab change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose]);

  if (!open) return null;

  const moveTab = (offset: number | 'first' | 'last') => {
    const index = tabs.findIndex((tab) => tab.id === activeTab);
    const nextIndex =
      offset === 'first' ? 0 : offset === 'last' ? tabs.length - 1 : (index + offset + tabs.length) % tabs.length;
    const next = tabs[nextIndex];
    onTabChange(next.id);
    tabRefs.current[next.id]?.focus();
  };

  return (
    <>
      <div className="fixed inset-0 z-[54] bg-slate-900/30" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="fixed inset-y-0 right-0 z-[55] flex w-full max-w-[720px] flex-col bg-white shadow-2xl"
      >
        <div className="border-b border-slate-200 px-5 pb-0 pt-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {context && <p className="truncate text-xs text-slate-500">{context}</p>}
              <h2 id={titleId} className="text-lg font-semibold text-slate-900">{title}</h2>
            </div>
            <button type="button" onClick={onClose} aria-label={t('close')} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100">
              <X className="h-5 w-5" aria-hidden />
            </button>
          </div>
          <div role="tablist" aria-label={t('label')} className="mt-3 flex gap-0.5 overflow-x-auto">
            {tabs.map((tab) => {
              const selected = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  ref={(element) => { tabRefs.current[tab.id] = element; }}
                  id={`${baseId}-tab-${tab.id}`}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls={`${baseId}-panel`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => onTabChange(tab.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'ArrowRight') { event.preventDefault(); moveTab(1); }
                    if (event.key === 'ArrowLeft') { event.preventDefault(); moveTab(-1); }
                    if (event.key === 'Home') { event.preventDefault(); moveTab('first'); }
                    if (event.key === 'End') { event.preventDefault(); moveTab('last'); }
                  }}
                  className={clsx(
                    'whitespace-nowrap border-b-2 px-3 py-2 text-sm',
                    selected ? 'border-indigo-600 font-medium text-indigo-700' : 'border-transparent text-slate-600 hover:text-slate-900',
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
        <div
          id={`${baseId}-panel`}
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-${activeTab}`}
          className="flex-1 overflow-y-auto px-5 py-4"
        >
          {children}
        </div>
      </div>
    </>
  );
}
