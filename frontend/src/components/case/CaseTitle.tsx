'use client';

import clsx from 'clsx';
import { compactApplicationTitle } from '@/lib/applicationDisplay';

interface CaseTitleProps {
  /** Full case title, shown on hover. */
  title: string;
  className?: string;
  /** Classes for the claim subject, e.g. to hide it on narrow screens. */
  subjectClassName?: string;
}

/** One-line case title: short holder name, lighter claim subject, full title on hover. */
export default function CaseTitle({ title, className, subjectClassName }: CaseTitleProps) {
  const { holder, subject } = compactApplicationTitle(title);
  return (
    <span className={clsx('block truncate', className)} title={title}>
      {holder}
      {subject && (
        <span className={clsx('font-normal text-slate-500', subjectClassName)}> · {subject}</span>
      )}
    </span>
  );
}
