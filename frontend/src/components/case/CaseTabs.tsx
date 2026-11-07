'use client';

import { useRef } from 'react';
import clsx from 'clsx';

export default function CaseTabs<T extends string>({
  tabs, active, onChange, idPrefix, label,
}: {
  tabs: ReadonlyArray<{ id: T; label: string }>;
  active: T;
  onChange: (id: T) => void;
  idPrefix: string;
  label: string;
}) {
  const refs = useRef<Partial<Record<T, HTMLButtonElement | null>>>({});
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map((tab, index) => (
        <button key={tab.id} ref={(node) => { refs.current[tab.id] = node; }}
          type="button" role="tab" id={`${idPrefix}-${tab.id}-tab`}
          aria-selected={active === tab.id} aria-controls={`${idPrefix}-${tab.id}-panel`}
          tabIndex={active === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => {
            const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
              : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
                : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
            if (next === null) return;
            event.preventDefault();
            onChange(tabs[next].id);
            refs.current[tabs[next].id]?.focus();
          }}
          className={clsx('rounded-lg border px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500',
            active === tab.id ? 'border-indigo-300 bg-indigo-50 text-indigo-900' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50')}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
