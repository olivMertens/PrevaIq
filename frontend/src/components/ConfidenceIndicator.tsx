'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';

interface ConfidenceIndicatorProps {
  confidence: number; // 0-1 scale
  fieldName?: string;
  size?: 'sm' | 'md';
}

export default function ConfidenceIndicator({
  confidence,
  fieldName,
  size = 'sm',
}: ConfidenceIndicatorProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const t = useTranslations('confidence');

  // Determine confidence level
  const getConfidenceLevel = (conf: number) => {
    if (conf >= 0.8) return { label: t('high'), color: 'bg-emerald-500', textColor: 'text-emerald-700' };
    if (conf >= 0.5) return { label: t('medium'), color: 'bg-amber-500', textColor: 'text-amber-700' };
    return { label: t('low'), color: 'bg-rose-500', textColor: 'text-rose-700' };
  };

  const level = getConfidenceLevel(confidence);
  const percentage = Math.round(confidence * 100);
  const sizeClass = size === 'sm' ? 'w-2 h-2' : 'w-3 h-3';

  return (
    <div className="relative inline-flex items-center">
      <button
        className={`${sizeClass} rounded-full ${level.color} cursor-help transition-transform hover:scale-125`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        aria-label={`Confidence: ${percentage}%`}
      />
      
      {showTooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
          <div className="bg-slate-800 text-white text-xs rounded-lg px-3 py-2 whitespace-nowrap shadow-lg">
            <div className="font-medium mb-1">
              {fieldName && <span className="text-slate-300">{fieldName}</span>}
            </div>
            <div className="flex items-center gap-2">
              <span className={`inline-block w-2 h-2 rounded-full ${level.color}`} />
              <span>{level.label} — {t('confidence')}</span>
              <span className="text-slate-400">({percentage}%)</span>
            </div>
          </div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
            <div className="border-4 border-transparent border-t-slate-800" />
          </div>
        </div>
      )}
    </div>
  );
}

// Helper component for displaying a value with its confidence
interface ConfidenceValueProps {
  value: string | number;
  confidence?: number;
  fieldName?: string;
  className?: string;
}

export function ConfidenceValue({
  value,
  confidence,
  fieldName,
  className = '',
}: ConfidenceValueProps) {
  if (confidence === undefined || confidence === null) {
    return <span className={className}>{value}</span>;
  }

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span>{value}</span>
      <ConfidenceIndicator confidence={confidence} fieldName={fieldName} />
    </span>
  );
}
