'use client';

import React, { useCallback, useRef } from 'react';

interface PageRefBadgeProps {
  page: number;
  onClick?: (page: number) => void;
  /** Called when the user hovers over the badge; receives the page number and the badge's bounding rect. */
  onHover?: (page: number, rect: DOMRect) => void;
  /** Called when the mouse leaves the badge. */
  onLeave?: () => void;
}

export default function PageRefBadge({ page, onClick, onHover, onLeave }: PageRefBadgeProps) {
  const btnRef = useRef<HTMLButtonElement>(null);

  const handleMouseEnter = useCallback(() => {
    if (onHover && btnRef.current) {
      onHover(page, btnRef.current.getBoundingClientRect());
    }
  }, [page, onHover]);

  return (
    <button
      ref={btnRef}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(page);
      }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={onLeave}
      className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-slate-100 text-slate-600 hover:bg-indigo-100 hover:text-indigo-700 transition-colors cursor-pointer border border-slate-200 hover:border-indigo-200"
      title={`Go to page ${page}`}
    >
      p.{page}
    </button>
  );
}

export function PageRefBadges({
  pages,
  onClick,
  onHover,
  onLeave,
}: {
  pages: number[];
  onClick?: (page: number) => void;
  onHover?: (page: number, rect: DOMRect) => void;
  onLeave?: () => void;
}) {
  if (!pages || pages.length === 0) return null;
  return (
    <span className="inline-flex items-center gap-1 ml-1">
      {pages.map((p) => (
        <PageRefBadge key={p} page={p} onClick={onClick} onHover={onHover} onLeave={onLeave} />
      ))}
    </span>
  );
}
