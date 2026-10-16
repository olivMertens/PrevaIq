'use client';

import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check, ClipboardList, Stethoscope, Landmark } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { usePersona } from '@/lib/PersonaContext';
import { getEnabledPersonas, PersonaConfig, PersonaId } from '@/lib/personas';
import clsx from 'clsx';
import { brand } from '@/lib/brand';

interface PlaceholderPersona {
  id: string;
  labelKey: string;
  enabled: false;
}

const PLACEHOLDER_PERSONAS: PlaceholderPersona[] = [
  { id: 'securities_lending', labelKey: 'securities_lending', enabled: false },
];

interface PersonaGroup {
  id: string;
  labelKey: 'underwriting' | 'claims' | 'wealth';
  icon: typeof ClipboardList;
  personaIds: PersonaId[];
  placeholders?: PlaceholderPersona[];
}

const PERSONA_GROUPS: PersonaGroup[] = [
  {
    id: 'underwriting',
    labelKey: 'underwriting',
    icon: ClipboardList,
    personaIds: ['underwriting', 'mortgage'],
  },
  {
    id: 'claims',
    labelKey: 'claims',
    icon: Stethoscope,
    personaIds: ['life_health_claims', 'automotive_claims', 'habitation_claims'],
  },
  {
    id: 'wealth',
    labelKey: 'wealth',
    icon: Landmark,
    personaIds: [],
    placeholders: [PLACEHOLDER_PERSONAS.find(p => p.id === 'securities_lending')!],
  },
];

export default function PersonaSelector() {
  const t = useTranslations('persona');
  const { currentPersona, personaConfig, setPersona } = usePersona();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const enabledPersonas = getEnabledPersonas();

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectPersona = (persona: PersonaConfig) => {
    if (persona.enabled) {
      setPersona(persona.id);
      setIsOpen(false);
    }
  };

  // Translate persona display name; fall back to the persona config name if a key is missing.
  const personaLabel = (id: PersonaId, fallback: string) => {
    try {
      return t(`labels.${id}`);
    } catch {
      return fallback;
    }
  };

  const currentUILabel = personaLabel(currentPersona, personaConfig.name);
  const IconComponent = personaConfig.icon;

  // Filter groups to only show those with at least one enabled persona OR placeholders
  const visibleGroups = PERSONA_GROUPS.map(group => ({
    ...group,
    personas: enabledPersonas.filter(p => group.personaIds.includes(p.id)),
  })).filter(group => group.personas.length > 0 || (group.placeholders && group.placeholders.length > 0));

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Selector Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
      >
        <IconComponent className="w-4 h-4" style={{ color: brand.primary }} />
        <span className="text-slate-700">{currentUILabel}</span>
        <ChevronDown 
          className={clsx(
            'w-4 h-4 text-slate-400 transition-transform',
            isOpen && 'rotate-180'
          )} 
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 mt-2 w-72 bg-white rounded-lg shadow-xl border border-slate-200 py-2 z-20">
            {visibleGroups.map((group, groupIndex) => {
              const GroupIcon = group.icon;
              return (
                <div key={group.id}>
                  {/* Group Header */}
                  <div className="px-4 py-1.5 flex items-center gap-2">
                    <GroupIcon className="w-4 h-4 text-slate-400" />
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                      {t(`groups.${group.labelKey}`)}
                    </span>
                  </div>
                  
                  {/* Group Items */}
                  {group.personas.map((persona) => {
                    const PersonaIcon = persona.icon;
                    const uiLabel = personaLabel(persona.id, persona.name);
                    return (
                      <button
                        key={persona.id}
                        onClick={() => handleSelectPersona(persona)}
                        className={clsx(
                          'w-full text-left px-4 py-2 text-sm transition-colors flex items-center gap-3 pl-8',
                          'hover:bg-slate-50 cursor-pointer',
                          currentPersona === persona.id && 'font-medium'
                        )}
                        style={currentPersona === persona.id ? { color: brand.primary, backgroundColor: `${brand.primary}0D` } : undefined}
                      >
                        <PersonaIcon className="w-4 h-4 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{uiLabel}</span>
                            {currentPersona === persona.id && (
                              <Check className="w-3 h-3" />
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                  
                  {/* Placeholder Items (Coming Soon) */}
                  {group.placeholders?.map((placeholder) => (
                    <div
                      key={placeholder.id}
                      className="w-full text-left px-4 py-2 text-sm flex items-center gap-3 pl-8 opacity-50 cursor-not-allowed"
                    >
                      <Landmark className="w-4 h-4 flex-shrink-0 text-slate-400" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-400">{t(`labels.${placeholder.labelKey}`)}</span>
                          <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-medium">
                            {t('comingSoon')}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                  
                  {/* Divider between groups */}
                  {groupIndex < visibleGroups.length - 1 && (
                    <div className="my-2 border-t border-slate-100" />
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
