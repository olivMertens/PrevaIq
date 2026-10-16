/**
 * Persona definitions and types for the workbench.
 * This module defines the available personas and their UI configurations.
 */

import { ClipboardList, HeartPulse, Home, Car, Stethoscope, CloudRain } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { brand } from './brand';

export type PersonaId = 'underwriting' | 'life_health_claims' | 'automotive_claims' | 'property_casualty_claims' | 'habitation_claims' | 'mortgage';

export interface Persona {
  id: PersonaId;
  name: string;
  description: string;
  icon: LucideIcon;
  color: string;
  enabled: boolean;
}

export interface PersonaConfig extends Persona {
  // UI-specific settings
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
}

/**
 * Persona registry with UI configurations
 */
export const PERSONAS: Record<PersonaId, PersonaConfig> = {
  underwriting: {
    id: 'underwriting',
    name: 'Souscription',
    description: 'Poste de travail de souscription pour le traitement des demandes et documents médicaux',
    icon: ClipboardList,
    color: brand.primary,
    enabled: true,
    primaryColor: brand.primary,
    secondaryColor: brand.secondary,
    accentColor: brand.accent,
  },
  life_health_claims: {
    id: 'life_health_claims',
    name: 'Sinistres Santé',
    description: 'Poste de travail de traitement des sinistres santé, vérification d\'éligibilité et adjudication',
    icon: Stethoscope,
    color: brand.primary,
    enabled: true,
    primaryColor: brand.primary,
    secondaryColor: brand.secondary,
    accentColor: brand.accent,
  },
  automotive_claims: {
    id: 'automotive_claims',
    name: 'Sinistres Auto',
    description: 'Poste de travail multimodal d\'évaluation des dommages automobiles avec traitement d\'images, vidéos et documents',
    icon: Car,
    color: '#dc2626',
    enabled: true,
    primaryColor: '#dc2626', // Red
    secondaryColor: '#ef4444',
    accentColor: '#b91c1c',
  },
  property_casualty_claims: {
    id: 'property_casualty_claims',
    name: 'Sinistres IARD (Ancien)',
    description: 'Ancien module IARD — utiliser Sinistres Habitation à la place',
    icon: Car,
    color: brand.primary,
    enabled: false, // Deprecated - use habitation_claims
    primaryColor: brand.primary,
    secondaryColor: brand.secondary,
    accentColor: brand.accent,
  },
  habitation_claims: {
    id: 'habitation_claims',
    name: 'Sinistres Habitation',
    description: 'Poste de travail de traitement des sinistres habitation — dégâts des eaux, tempêtes, catastrophes naturelles, avec photos et documents',
    icon: CloudRain,
    color: '#2563eb',
    enabled: true,
    primaryColor: '#2563eb', // Blue
    secondaryColor: '#3b82f6',
    accentColor: '#1d4ed8',
  },
  mortgage: {
    id: 'mortgage',
    name: 'Souscription Hypothécaire',
    description: 'Poste de travail de souscription hypothécaire avec vérifications de conformité BSIF B-20',
    icon: Home,
    color: '#059669',
    enabled: true,
    primaryColor: '#059669', // Emerald
    secondaryColor: '#10b981',
    accentColor: '#047857',
  },
};

/**
 * Get persona configuration by ID
 */
export function getPersona(id: PersonaId): PersonaConfig {
  return PERSONAS[id];
}

/**
 * Get all available personas
 */
export function getAllPersonas(): PersonaConfig[] {
  return Object.values(PERSONAS);
}

/**
 * Get only enabled personas
 */
export function getEnabledPersonas(): PersonaConfig[] {
  return Object.values(PERSONAS).filter(p => p.enabled);
}

/**
 * Default persona
 */
export const DEFAULT_PERSONA: PersonaId = 'underwriting';

/**
 * Local storage key for persisting selected persona
 */
export const PERSONA_STORAGE_KEY = 'workbenchiq-persona';
