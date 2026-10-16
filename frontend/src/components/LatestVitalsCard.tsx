'use client';

import React from 'react';
import { Heart, Thermometer, Wind, Droplets, Weight, Ruler } from 'lucide-react';
import { PageRefBadges } from './PageRefBadge';
import type { LatestVitalsData } from '@/lib/types';
import { useTranslations } from 'next-intl';

interface LatestVitalsCardProps {
  vitals: LatestVitalsData | null;
  onPageClick?: (page: number) => void;
  onPageHover?: (page: number, rect: DOMRect) => void;
  onPageLeave?: () => void;
}

interface VitalItemProps {
  icon: React.ReactNode;
  label: string;
  value: string | number | null;
  unit?: string;
  color: string;
}

function VitalItem({ icon, label, value, unit, color }: VitalItemProps) {
  return (
    <div className="flex flex-col items-center p-2.5 rounded-lg bg-slate-50 border border-slate-100">
      <div className={`mb-1 ${color}`}>{icon}</div>
      <span className="text-[10px] text-slate-500 font-medium uppercase mb-1">{label}</span>
      {value !== null && value !== undefined ? (
        <span className="text-sm font-semibold text-slate-800">
          {value}{unit ? ` ${unit}` : ''}
        </span>
      ) : (
        <span className="text-xs text-slate-400 italic">N/A</span>
      )}
    </div>
  );
}

export default function LatestVitalsCard({ vitals, onPageClick, onPageHover, onPageLeave }: LatestVitalsCardProps) {
  const t = useTranslations('vitals');
  if (!vitals) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2 mb-2">
          <Heart className="w-4 h-4 text-red-500" /> {t('latestVitals')}
        </h3>
        <p className="text-sm text-slate-500 italic">{t('noData')}</p>
      </div>
    );
  }

  const bp = vitals.blood_pressure
    ? `${vitals.blood_pressure.systolic}/${vitals.blood_pressure.diastolic}`
    : null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <Heart className="w-4 h-4 text-red-500" /> {t('latestVitals')}
        </h3>
        <div className="flex items-center gap-2">
          {vitals.date && <span className="text-xs text-slate-500">{vitals.date}</span>}
          <PageRefBadges pages={vitals.page_references} onClick={onPageClick} onHover={onPageHover} onLeave={onPageLeave} />
        </div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
        <VitalItem
          icon={<Heart className="w-4 h-4" />}
          label="BP"
          value={bp}
          unit="mmHg"
          color="text-red-500"
        />
        <VitalItem
          icon={<Heart className="w-4 h-4" />}
          label="HR"
          value={vitals.heart_rate}
          unit="bpm"
          color="text-pink-500"
        />
        <VitalItem
          icon={<Weight className="w-4 h-4" />}
          label="Weight"
          value={vitals.weight?.value ?? null}
          unit={vitals.weight?.unit || 'lbs'}
          color="text-blue-500"
        />
        <VitalItem
          icon={<Ruler className="w-4 h-4" />}
          label="Height"
          value={vitals.height?.value ?? null}
          color="text-indigo-500"
        />
        <VitalItem
          icon={<Droplets className="w-4 h-4" />}
          label="BMI"
          value={vitals.bmi}
          color="text-emerald-500"
        />
        <VitalItem
          icon={<Thermometer className="w-4 h-4" />}
          label="Temp"
          value={vitals.temperature}
          unit="°F"
          color="text-orange-500"
        />
        <VitalItem
          icon={<Wind className="w-4 h-4" />}
          label="RR"
          value={vitals.respiratory_rate}
          unit="/min"
          color="text-cyan-500"
        />
        <VitalItem
          icon={<Droplets className="w-4 h-4" />}
          label="SpO2"
          value={vitals.oxygen_saturation}
          unit="%"
          color="text-teal-500"
        />
      </div>
    </div>
  );
}
