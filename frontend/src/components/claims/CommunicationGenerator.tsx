'use client';

import React, { useState, useCallback } from 'react';
import { Mail, MessageSquare, FileText, Copy, Check, X, Loader2, Sparkles, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';
import { brand } from '@/lib/brand';

const BRAND = brand.companyName;
const PHONE = brand.insurerPhone;

interface CommunicationGeneratorProps {
  /** Application ID for API call */
  applicationId: string;
  /** Insured person name */
  insuredName: string;
  /** Claim/case reference */
  claimReference: string;
  /** Current decision status */
  decisionStatus?: 'approved' | 'pending' | 'denied' | 'investigation' | null;
  /** Settlement amount if approved */
  settlementAmount?: string;
  /**
   * Initial tone selection. When omitted, defaults to 'standard'. Callers can
   * pass 'empathetic' when client sentiment is stressed/critical so the UI
   * reflects the recommended tone before the agent clicks Generate.
   */
  defaultTone?: 'empathetic' | 'standard' | 'formal';
}

type CommType = 'email' | 'sms' | 'letter';
type CommTone = 'empathetic' | 'standard' | 'formal';

interface GeneratedComm {
  type: CommType;
  tone: CommTone;
  subject?: string;
  body: string;
  timestamp: string;
}

const COMM_TYPES: { id: CommType; label: string; icon: typeof Mail }[] = [
  { id: 'email', label: 'Email', icon: Mail },
  { id: 'sms', label: 'SMS', icon: MessageSquare },
  { id: 'letter', label: 'Courrier', icon: FileText },
];

const TONE_OPTIONS: { id: CommTone; label: string; desc: string }[] = [
  { id: 'empathetic', label: 'Empathique', desc: `Ton chaleureux, proximité et écoute — valeurs ${BRAND}` },
  { id: 'standard', label: 'Standard', desc: 'Professionnel et bienveillant' },
  { id: 'formal', label: 'Formel', desc: 'Officiel, termes juridiques' },
];

const TEMPLATES: Record<string, Record<CommType, { subject?: string; body: string }>> = {
  approved: {
    email: {
      subject: 'Votre sinistre {ref} — Bonne nouvelle, votre indemnisation est validée',
      body: `Bonjour {name},

Nous sommes heureux de vous confirmer que votre déclaration de sinistre n° {ref} a été analysée et que votre indemnisation a été validée.

**Montant accordé** : {amount}
**Délai de versement** : sous 5 jours ouvrés

Le montant sera versé directement sur votre compte bancaire enregistré dans votre contrat.

En tant que client ${BRAND}, nous sommes à vos côtés tout au long de cette épreuve. N'hésitez pas à contacter votre conseiller dédié au ${PHONE} si vous avez la moindre question.

Bien à vous,
Votre équipe ${BRAND} Sinistres`,
    },
    sms: {
      body: `${BRAND} : Bonne nouvelle ! Votre sinistre n\u00b0{ref} est valid\u00e9. Indemnisation de {amount} sous 5 jours. Votre conseiller reste \u00e0 votre \u00e9coute au ${PHONE}`,
    },
    letter: {
      subject: 'Notification d\'indemnisation — Sinistre n° {ref}',
      body: `Madame, Monsieur {name},

Par la présente, nous vous notifions que votre déclaration de sinistre enregistrée sous la référence {ref} a fait l'objet d'une analyse complète.

Conformément aux conditions générales de votre contrat Multirisque Habitation, l'indemnisation suivante vous est accordée :

Montant brut de l'indemnisation : {amount}
Franchise applicable : selon votre contrat
Montant net à percevoir : sera précisé dans le décompte de règlement joint

Le versement sera effectué dans un délai de cinq (5) jours ouvrés.

Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées.

Service Sinistres — ${BRAND}`,
    },
  },
  pending: {
    email: {
      subject: 'Votre sinistre {ref} — Complément d\'information nécessaire',
      body: `Bonjour {name},

Nous avons bien reçu votre déclaration de sinistre n° {ref} et nous vous remercions de votre confiance.

Nous souhaitons traiter votre dossier dans les meilleurs délais. Pour cela, pourriez-vous nous transmettre les éléments suivants :
- Factures ou devis des réparations
- Photos complémentaires des dommages
- Tout justificatif de propriété des biens endommagés

Vous pouvez déposer ces documents directement sur votre espace client ou les envoyer par email.

Nous avançons ensemble — votre conseiller ${BRAND} est à votre disposition au ${PHONE} pour vous accompagner.

Bien à vous,
Votre équipe ${BRAND} Sinistres`,
    },
    sms: {
      body: `${BRAND} : Sinistre n\u00b0{ref} en cours d'\u00e9tude. Des documents compl\u00e9mentaires sont n\u00e9cessaires. Votre conseiller vous accompagne : ${PHONE} ou espace client.`,
    },
    letter: {
      subject: 'Demande de pièces complémentaires — Sinistre n° {ref}',
      body: `Madame, Monsieur {name},

Nous accusons réception de votre déclaration de sinistre n° {ref}.

Afin de poursuivre l'instruction de votre dossier, nous vous prions de bien vouloir nous transmettre les pièces suivantes dans un délai de 30 jours :

1. Factures ou devis relatifs aux dommages déclarés
2. Photographies complémentaires
3. Justificatifs de propriété des biens concernés

À défaut de réception de ces documents dans le délai imparti, votre dossier pourrait faire l'objet d'une clôture.

Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées.

Service Sinistres — ${BRAND}`,
    },
  },
  denied: {
    email: {
      subject: 'Votre sinistre {ref} — Décision de non-prise en charge',
      body: `Bonjour {name},

Après analyse approfondie de votre déclaration de sinistre n° {ref}, nous sommes au regret de vous informer que celui-ci ne peut être pris en charge au titre de votre contrat.

**Motif** : Les conditions de garantie ne sont pas réunies pour ce type de sinistre.

Nous comprenons que cette décision puisse être décevante. Votre conseiller ${BRAND} se tient à votre disposition pour vous expliquer en détail les raisons de cette décision et étudier avec vous d'éventuelles alternatives.

Vous disposez d'un droit de contestation dans un délai de 2 mois. Pour ce faire, adressez votre courrier au Service Réclamations.

Nous restons à votre écoute.

Bien à vous,
Votre équipe ${BRAND} Sinistres`,
    },
    sms: {
      body: `${BRAND} : Sinistre n°{ref} — Votre dossier ne peut être pris en charge. Votre conseiller est disponible pour en discuter avec vous : ${PHONE}`,
    },
    letter: {
      subject: 'Notification de non-prise en charge — Sinistre n° {ref}',
      body: `Madame, Monsieur {name},

À la suite de l'examen de votre déclaration de sinistre n° {ref}, nous avons le regret de vous informer que les conditions de garantie prévues par votre contrat ne permettent pas la prise en charge du sinistre déclaré.

Vous disposez de la possibilité de contester cette décision auprès de notre Service Réclamations dans un délai de deux (2) mois à compter de la réception du présent courrier.

Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées.

Service Sinistres — ${BRAND}`,
    },
  },
};

export default function CommunicationGenerator({
  applicationId,
  insuredName,
  claimReference,
  decisionStatus,
  settlementAmount,
  defaultTone = 'standard',
}: CommunicationGeneratorProps) {
  const tComm = useTranslations('communicationActions');
  const [commType, setCommType] = useState<CommType>('email');
  const [tone, setTone] = useState<CommTone>(defaultTone);
  const [generated, setGenerated] = useState<GeneratedComm | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showToneOptions, setShowToneOptions] = useState(false);

  const handleGenerate = useCallback(async () => {
    setIsGenerating(true);
    try {
      const response = await fetch(`/api/applications/${applicationId}/generate-communication`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel: commType, tone }),
      });
      if (!response.ok) throw new Error(`API error: ${response.status}`);
      const result = await response.json();

      setGenerated({
        type: commType,
        tone,
        subject: result.subject || undefined,
        body: result.body || '',
        timestamp: result.generated_at || new Date().toISOString(),
      });
    } catch (err) {
      console.error('[CommunicationGenerator] Generation failed:', err);
      // Fallback to template if API fails
      const status = decisionStatus || 'pending';
      const template = TEMPLATES[status]?.[commType] || TEMPLATES.pending[commType];
      const replacements: Record<string, string> = {
        '{name}': insuredName || 'Client',
        '{ref}': claimReference || applicationId.slice(0, 8),
        '{amount}': settlementAmount || '—',
      };
      let body = template.body;
      let subject = template.subject;
      for (const [key, val] of Object.entries(replacements)) {
        body = body.replaceAll(key, val);
        if (subject) subject = subject.replaceAll(key, val);
      }
      if (tone === 'empathetic') {
        body = body.replace('Bonjour', 'Cher(e)');
      }
      setGenerated({ type: commType, tone, subject, body, timestamp: new Date().toISOString() });
    } finally {
      setIsGenerating(false);
    }
  }, [commType, tone, applicationId, decisionStatus, insuredName, claimReference, settlementAmount]);

  const handleCopy = useCallback(async () => {
    if (!generated) return;
    const text = generated.subject ? `Objet: ${generated.subject}\n\n${generated.body}` : generated.body;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  }, [generated]);

  return (
    <div className="space-y-3">
      {/* Type selector */}
      <div className="flex items-center gap-2">
        {COMM_TYPES.map((ct) => {
          const Icon = ct.icon;
          return (
            <button
              key={ct.id}
              onClick={() => { setCommType(ct.id); setGenerated(null); }}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                commType === ct.id
                  ? ''
                  : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'
              )}
              style={commType === ct.id ? {
                color: brand.primary,
                borderColor: `${brand.primary}33`,
                backgroundColor: `${brand.primary}0D`,
              } : undefined}
            >
              <Icon className="w-3.5 h-3.5" />
              {ct.label}
            </button>
          );
        })}
        {/* Tone dropdown */}
        <div className="relative ml-auto">
          <button
            onClick={() => setShowToneOptions(!showToneOptions)}
            className="flex items-center gap-1 px-2 py-1.5 text-[10px] text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg bg-white"
          >
            Ton : {TONE_OPTIONS.find(t => t.id === tone)?.label}
            <ChevronDown className="w-3 h-3" />
          </button>
          {showToneOptions && (
            <div className="absolute right-0 top-full mt-1 z-10 w-48 bg-white rounded-lg shadow-lg border border-slate-200 py-1">
              {TONE_OPTIONS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setTone(t.id); setShowToneOptions(false); setGenerated(null); }}
                  className={clsx(
                    'w-full text-left px-3 py-2 text-xs hover:bg-slate-50',
                    tone === t.id ? '' : 'text-slate-600'
                  )}
                  style={tone === t.id ? { color: brand.primary, backgroundColor: `${brand.primary}0D` } : undefined}
                >
                  <div className="font-medium">{t.label}</div>
                  <div className="text-[10px] text-slate-400">{t.desc}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Generate or display */}
      {!generated ? (
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          style={{ backgroundColor: brand.primary }}
        >
          {isGenerating ? (
            <><Loader2 className="w-4 h-4 animate-spin" />Génération IA...</>
          ) : (
            <><Sparkles className="w-4 h-4" />Générer {commType === 'email' ? 'l\'email' : commType === 'sms' ? 'le SMS' : 'le courrier'}</>
          )}
        </button>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5" style={{ color: brand.primary }} />
            <span className="text-xs font-medium text-slate-700">
              {commType === 'email' ? 'Email' : commType === 'sms' ? 'SMS' : 'Courrier'} généré
            </span>
            <span className="text-[10px] text-slate-400">({TONE_OPTIONS.find(t => t.id === tone)?.label})</span>
            <div className="ml-auto flex items-center gap-1">
              <button onClick={handleCopy} title={tComm('copy')}
                className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
              <button onClick={() => setGenerated(null)} title={tComm('close')}
                className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          {/* Subject (email/letter only) */}
          {generated.subject && (
            <div className="px-3 py-1.5 border-b border-slate-100 text-xs">
              <span className="text-slate-400">Objet : </span>
              <span className="font-medium text-slate-800">{generated.subject}</span>
            </div>
          )}
          {/* Body */}
          <div className="px-3 py-3 text-xs text-slate-700 whitespace-pre-line leading-relaxed max-h-48 overflow-auto">
            {generated.body}
          </div>
          {/* Footer actions */}
          <div className="px-3 py-2 bg-slate-50 border-t border-slate-100 flex items-center gap-2">
            <button
              onClick={handleGenerate}
              className="flex items-center gap-1 px-2.5 py-1 text-[10px] font-medium border rounded transition-colors"
              style={{
                color: brand.primary,
                borderColor: `${brand.primary}33`,
                backgroundColor: `${brand.primary}0D`,
              }}
            >
              <Sparkles className="w-3 h-3" />Régénérer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
