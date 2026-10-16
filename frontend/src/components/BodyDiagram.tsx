'use client';

import React from 'react';
import type { BodySystemEntry, BodyRegion, Severity } from '@/lib/types';
import { useTranslations } from 'next-intl';

interface BodyDiagramProps {
  bodySystems: BodySystemEntry[];
  onRegionClick?: (systemCode: string) => void;
  selectedSystemCode?: string;
}

// Map body regions to SVG areas
const regionPaths: Record<BodyRegion, { path: string; cx: number; cy: number; label: string }> = {
  head: {
    path: 'M45,8 Q50,2 55,8 Q60,14 58,22 L56,28 Q50,30 44,28 L42,22 Q40,14 45,8 Z',
    cx: 50,
    cy: 16,
    label: 'Head',
  },
  chest: {
    path: 'M36,34 L44,30 Q50,29 56,30 L64,34 L66,50 L62,56 Q50,58 38,56 L34,50 Z',
    cx: 50,
    cy: 44,
    label: 'Chest',
  },
  abdomen: {
    path: 'M38,56 Q50,58 62,56 L63,68 Q50,70 37,68 Z',
    cx: 50,
    cy: 62,
    label: 'Abdomen',
  },
  pelvis: {
    path: 'M37,68 Q50,70 63,68 L65,76 Q50,80 35,76 Z',
    cx: 50,
    cy: 73,
    label: 'Pelvis',
  },
  joints_spine: {
    path: 'M47,30 L53,30 L53,76 L47,76 Z',
    cx: 50,
    cy: 53,
    label: 'Spine & Joints',
  },
  extremities: {
    path: 'M28,34 L36,34 L34,50 L30,60 L24,50 Z M64,34 L72,34 L76,50 L70,60 L66,50 Z',
    cx: 50,
    cy: 47,
    label: 'Extremities',
  },
  skin: {
    // Not rendered as a specific region — whole body outline
    path: '',
    cx: 50,
    cy: 50,
    label: 'Skin',
  },
  systemic: {
    // Not rendered as a specific region — indicator near center
    path: '',
    cx: 78,
    cy: 50,
    label: 'Systemic',
  },
};

const severityColors: Record<Severity, { fill: string; stroke: string; className: string }> = {
  high: { fill: 'rgba(239,68,68,0.35)', stroke: '#ef4444', className: 'text-red-600' },
  moderate: { fill: 'rgba(245,158,11,0.3)', stroke: '#f59e0b', className: 'text-amber-600' },
  low: { fill: 'rgba(34,197,94,0.25)', stroke: '#22c55e', className: 'text-emerald-600' },
  normal: { fill: 'rgba(148,163,184,0.15)', stroke: '#94a3b8', className: 'text-slate-400' },
};

/** Aggregate body systems by region, picking the highest severity */
function getRegionData(bodySystems: BodySystemEntry[]) {
  const regionMap = new Map<BodyRegion, { severity: Severity; systems: BodySystemEntry[]; diagnosisCount: number }>();
  const severityRank: Record<Severity, number> = { high: 3, moderate: 2, low: 1, normal: 0 };

  for (const sys of bodySystems) {
    const region = sys.body_region as BodyRegion;
    const existing = regionMap.get(region);
    const dxCount = sys.diagnoses?.length || 0;
    if (existing) {
      existing.systems.push(sys);
      existing.diagnosisCount += dxCount;
      if (severityRank[sys.severity] > severityRank[existing.severity]) {
        existing.severity = sys.severity;
      }
    } else {
      regionMap.set(region, { severity: sys.severity, systems: [sys], diagnosisCount: dxCount });
    }
  }
  return regionMap;
}

export default function BodyDiagram({ bodySystems, onRegionClick, selectedSystemCode }: BodyDiagramProps) {
  const t = useTranslations('body');
  const regionData = getRegionData(bodySystems);
  const selectedRegion = bodySystems.find((s) => s.system_code === selectedSystemCode)?.body_region;

  // Find all system codes with their regions for click handling
  const regionToFirstSystem = new Map<BodyRegion, string>();
  for (const sys of bodySystems) {
    if (!regionToFirstSystem.has(sys.body_region as BodyRegion)) {
      regionToFirstSystem.set(sys.body_region as BodyRegion, sys.system_code);
    }
  }

  return (
    <div className="relative bg-slate-50 rounded-xl p-4">
      <h4 className="text-sm font-medium text-slate-700 mb-3">{t('systemMap')}</h4>
      <div className="relative mx-auto" style={{ maxWidth: 180 }}>
        <svg viewBox="0 0 100 100" className="w-full h-full">
          {/* Human silhouette outline */}
          <g opacity={0.2} stroke="#94a3b8" strokeWidth="0.8" fill="none">
            {/* Head */}
            <ellipse cx="50" cy="14" rx="8" ry="10" />
            {/* Neck */}
            <line x1="47" y1="24" x2="47" y2="30" />
            <line x1="53" y1="24" x2="53" y2="30" />
            {/* Torso */}
            <path d="M36,34 L44,30 Q50,29 56,30 L64,34 L66,50 L63,68 L65,76 Q50,80 35,76 L37,68 L34,50 Z" />
            {/* Left arm */}
            <path d="M36,34 L28,34 L24,50 L26,62 L30,60" />
            {/* Right arm */}
            <path d="M64,34 L72,34 L76,50 L74,62 L70,60" />
            {/* Left leg */}
            <path d="M35,76 L32,90 L30,98 L36,98 L38,90 L42,78" />
            {/* Right leg */}
            <path d="M65,76 L68,90 L70,98 L64,98 L62,90 L58,78" />
          </g>

          {/* Highlighted regions based on findings */}
          {Array.from(regionData.entries()).map(([region, data]) => {
            const rp = regionPaths[region];
            if (!rp || !rp.path) return null;
            const colors = severityColors[data.severity];
            const isSelected = region === selectedRegion;

            return (
              <g key={region}>
                <path
                  d={rp.path}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={isSelected ? 1.5 : 0.8}
                  opacity={isSelected ? 1 : 0.8}
                  className="cursor-pointer transition-all duration-200"
                  onClick={() => {
                    const code = regionToFirstSystem.get(region);
                    if (code) onRegionClick?.(code);
                  }}
                >
                  <title>{`${rp.label}: ${data.systems.map(s => s.system_name).join(', ')} — ${data.severity}`}</title>
                </path>
                {/* Diagnosis count indicator */}
                {data.diagnosisCount > 0 && (
                  <>
                    <circle
                      cx={rp.cx}
                      cy={rp.cy}
                      r={5}
                      fill={colors.stroke}
                      opacity={0.9}
                      className="cursor-pointer"
                      onClick={() => {
                        const code = regionToFirstSystem.get(region);
                        if (code) onRegionClick?.(code);
                      }}
                    />
                    <text
                      x={rp.cx}
                      y={rp.cy}
                      dy="0.35em"
                      textAnchor="middle"
                      fill="white"
                      fontSize="6"
                      fontWeight="bold"
                      className="pointer-events-none"
                    >
                      {data.diagnosisCount}
                    </text>
                  </>
                )}
              </g>
            );
          })}

          {/* Systemic indicator (outside body) */}
          {regionData.has('systemic') && (() => {
            const data = regionData.get('systemic')!;
            const colors = severityColors[data.severity];
            return (
              <g>
                <circle
                  cx={82}
                  cy={50}
                  r={5}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={0.8}
                  className="cursor-pointer"
                  onClick={() => {
                    const code = regionToFirstSystem.get('systemic');
                    if (code) onRegionClick?.(code);
                  }}
                >
                  <title>{`Systemic: ${data.systems.map(s => s.system_name).join(', ')} — ${data.severity}`}</title>
                </circle>
                <text
                  x={82}
                  y={50}
                  dy="0.35em"
                  textAnchor="middle"
                  fill={colors.stroke}
                  fontSize="5"
                  fontWeight="bold"
                  className="pointer-events-none"
                >
                  {data.diagnosisCount}
                </text>
                <text x={82} y={58} textAnchor="middle" fill="#64748b" fontSize="3.5">{t('systemic')}</text>
              </g>
            );
          })()}

          {/* Skin indicator (outside body) */}
          {regionData.has('skin') && (() => {
            const data = regionData.get('skin')!;
            const colors = severityColors[data.severity];
            return (
              <g>
                <circle
                  cx={18}
                  cy={50}
                  r={5}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={0.8}
                  className="cursor-pointer"
                  onClick={() => {
                    const code = regionToFirstSystem.get('skin');
                    if (code) onRegionClick?.(code);
                  }}
                >
                  <title>{`Skin: ${data.systems.map(s => s.system_name).join(', ')} — ${data.severity}`}</title>
                </circle>
                <text
                  x={18}
                  y={50}
                  dy="0.35em"
                  textAnchor="middle"
                  fill={colors.stroke}
                  fontSize="5"
                  fontWeight="bold"
                  className="pointer-events-none"
                >
                  {data.diagnosisCount}
                </text>
                <text x={18} y={58} textAnchor="middle" fill="#64748b" fontSize="3.5">{t('skin')}</text>
              </g>
            );
          })()}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-3 mt-4">
        {(['high', 'moderate', 'low', 'normal'] as Severity[]).map((sev) => (
          <div key={sev} className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: severityColors[sev].stroke }}
            />
            <span className="text-[10px] text-slate-500 capitalize">{t(sev)}</span>
          </div>
        ))}
      </div>

      {/* Summary stats */}
      <div className="mt-3 text-center">
        <span className="text-xs text-slate-500">
          {t('findingsCount', { count: bodySystems.length })}
        </span>
      </div>
    </div>
  );
}
