'use client';

import { useState } from 'react';
import { useLocale } from 'next-intl';
import { HelpCircle, X, ChevronDown, ChevronRight, Upload, MessageSquare, CheckCircle, Search, CloudRain, FileText, Image as ImageIcon, ClipboardList, Car, Home, Shield, Users, Stethoscope } from 'lucide-react';
import clsx from 'clsx';
import { brand } from '@/lib/brand';

interface Step {
  icon: typeof Upload;
  title: string;
  titleEn: string;
  detail: string;
  detailEn: string;
  tip?: string;
  tipEn?: string;
}

interface Scenario {
  id: string;
  label: string;
  labelEn: string;
  icon: typeof CloudRain;
  color: string;
  summary: string;
  summaryEn: string;
  demoPdf: string;
  steps: Step[];
}

const DEMO_DIR = brand.demoAssetsDir;
const CUSTOMER_ID = (n: string) => `${brand.customerIdPrefix}-${n}`;

const SCENARIOS: Scenario[] = [
  {
    id: 'habitation',
    label: 'Sinistres Habitation',
    labelEn: 'Property Claims',
    icon: CloudRain,
    color: '#2563eb',
    summary: 'Olivier MERTENS LAFFITE (mlo@wine.com) — Tempête Gérard 27/03/2026 — Cave inondée, collection de vins détruite — 10 825 €\nDossier E0FF1B47 — 4 photos + 1 PDF (déclaration assureur)',
    summaryEn: 'Olivier MERTENS LAFFITE (mlo@wine.com) — Storm Gérard 03/27/2026 — Flooded cellar, wine collection destroyed — €10,825\nFile E0FF1B47 — 4 photos + 1 PDF (insurer claim form)',
    demoPdf: `${DEMO_DIR}/habitation/declaration-sinistre-habitation.pdf`,
    steps: [
      {
        icon: CloudRain,
        title: '1. Sélectionner "Sinistres Habitation"',
        titleEn: '1. Select "Property Claims"',
        detail: 'Sélecteur de persona en haut → groupe "Sinistres" → "Sinistres Habitation" (pictogramme nuage/pluie).',
        detailEn: 'Top persona selector → "Claims" group → "Property Claims" (cloud/rain line icon).',
        tip: 'Accepte PDF + images. Le RAG cherche dans les conditions générales habitation indexées.',
        tipEn: 'Accepts PDF + images. RAG searches the indexed habitation policy terms.',
      },
      {
        icon: Upload,
        title: '2. Uploader les documents',
        titleEn: '2. Upload documents',
        detail: '• declaration-sinistre-habitation.pdf (déclaration assureur)\n• 4 photos de la cave inondée, murs endommagés, bouteilles détruites (PNG/JPG)\n\nUtiliser "Nouveau dossier" ou glisser-déposer les fichiers dans la zone du tableau de bord : le traitement démarre automatiquement.',
        detailEn: '• declaration-sinistre-habitation.pdf (insurer claim form)\n• 4 photos of flooded cellar, damaged walls, broken bottles (PNG/JPG)\n\nUse "New Application" or drag and drop the files into the dashboard drop zone: processing starts automatically.',
        tip: `Le PDF est dans ${DEMO_DIR}/habitation/.`,
        tipEn: `PDF is in ${DEMO_DIR}/habitation/.`,
      },
      {
        icon: FileText,
        title: '3. Observer le traitement IA (2-3 min)',
        titleEn: '3. Watch AI processing (2-3 min)',
        detail: '① Extraction → Content Understanding / MarkItDown structure les champs et pièces jointes\n② Analyse multimodale → qualifie les photos de dégâts\n③ Analyse LLM + RAG → évalue le sinistre et cite les conditions applicables',
        detailEn: '① Extraction engine → Content Understanding / MarkItDown structures fields and attachments\n② Multimodal analysis → qualifies damage photos\n③ LLM analysis + RAG → evaluates the claim and cites applicable policy terms',
      },
      {
        icon: Shield,
        title: '4. Analyse Anti-Fraude & Cat-Nat',
        titleEn: '4. Anti-Fraud & Cat-Nat Analysis',
        detail: 'Bouton "Analyse Anti-Fraude" → lance l\'agent Bing Grounding :\n• Vérifie l\'arrêté Cat-Nat pour la commune + la date\n• Croise les déclarations avec les sources publiques\n• Étiquette contextuelle "✓ Cat-Nat confirmée" ou "✗ non confirmée"\n\nAttention : indicateurs de fraude + score global.',
        detailEn: '"Anti-Fraud Analysis" button → launches Bing Grounding agent:\n• Verifies Cat-Nat decree for municipality + date\n• Cross-references declarations with public sources\n• Context label "✓ Cat-Nat confirmed" or "✗ not confirmed"\n\nNote: fraud indicators + overall score.',
        tip: 'L\'analyse web prend 30-60s. Les sources sont cliquables.',
        tipEn: 'Web analysis takes 30-60s. Sources are clickable.',
      },
      {
        icon: MessageSquare,
        title: '5. Ask IQ (Chat RAG)',
        titleEn: '5. Ask IQ (RAG Chat)',
        detail: 'Bouton Ask IQ en bas à droite dans le workbench. Questions suggérées :\n\n→ "Ce sinistre est-il couvert par les CG Habitation ?"\n→ "Quel est le montant de la franchise tempête ?"\n→ "Les vins en cave sont-ils des objets de valeur ?"',
        detailEn: 'Ask IQ button in the bottom-right of the workbench. Suggested questions:\n\n→ "Is this claim covered by the Housing policy?"\n→ "What is the storm deductible?"\n→ "Are wines in a cellar considered valuables?"',
        tip: 'Cliquer "X polices référencées" pour voir les articles cités.',
        tipEn: 'Click "X policies referenced" to see cited articles.',
      },
      {
        icon: CheckCircle,
        title: '6. Décision du gestionnaire',
        titleEn: '6. Adjuster decision',
        detail: 'Approuver / Ajuster / Refuser avec notes.\nEx: "Couvert Art. 3.2 CG Habitation, franchise 250€ déduite."',
        detailEn: 'Approve / Adjust / Deny with notes.\nEx: "Covered per Art. 3.2, €250 deductible applied."',
      },
    ],
  },
  {
    id: 'auto',
    label: 'Sinistres Auto',
    labelEn: 'Auto Claims',
    icon: Car,
    color: '#dc2626',
    summary: 'Accident de stationnement — portière enfoncée — Constat amiable + photo dégât\nDossier thread2 — 2 PDF + 1 photo',
    summaryEn: 'Parking accident — dented door — Mutual claim form + damage photo\nFile thread2 — 2 PDFs + 1 photo',
    demoPdf: `${DEMO_DIR}/carcrash2/thread2-01-client-accident-auto.pdf`,
    steps: [
      {
        icon: Car,
        title: '1. Sélectionner "Sinistres Auto"',
        titleEn: '1. Select "Auto Claims"',
        detail: 'Sélecteur de persona en haut → groupe "Sinistres" → "Sinistres Auto" (pictogramme voiture).',
        detailEn: 'Top persona selector → "Claims" group → "Auto Claims" (car line icon).',
        tip: 'Le RAG cherche dans les CG Auto et CG Flotte Auto indexées.',
        tipEn: 'RAG searches the indexed Auto and Fleet Auto policy terms.',
      },
      {
        icon: Upload,
        title: '2. Uploader les documents',
        titleEn: '2. Upload documents',
        detail: `• thread2-01-client-accident-auto.pdf (déclaration client)\n• thread2-02-${brand.key}-reponse-auto.pdf (réponse assureur)\n• crash_portière_enfoncée.png (photo du dégât)\n\nUtiliser "Nouveau dossier" ou glisser-déposer les fichiers. Cette persona accepte aussi les vidéos.`,
        detailEn: `• thread2-01-client-accident-auto.pdf (client declaration)\n• thread2-02-${brand.key}-reponse-auto.pdf (insurer response)\n• crash_portière_enfoncée.png (damage photo)\n\nUse "New Application" or drag and drop the files. This persona also accepts videos.`,
        tip: `Fichiers dans ${DEMO_DIR}/carcrash2/.`,
        tipEn: `Files in ${DEMO_DIR}/carcrash2/.`,
      },
      {
        icon: FileText,
        title: '3. Traitement IA multimodal',
        titleEn: '3. Multimodal AI processing',
        detail: '① Extraction → extrait le message client et les pièces jointes\n② Analyse multimodale → analyse la photo de dégât véhicule\n③ Vue Auto dédiée → documents, estimation, responsabilité et indicateurs de fraude dans le même écran',
        detailEn: '① Extraction engine → extracts the client message and attachments\n② Multimodal analysis → analyzes the vehicle damage photo\n③ Dedicated Auto view → documents, estimate, liability and fraud indicators in the same screen',
      },
      {
        icon: Search,
        title: '4. Résultats & responsabilité',
        titleEn: '4. Results & liability',
        detail: '• Analyse de responsabilité → répartition des torts\n• Estimation des réparations → montants par poste\n• Convention IRSA → application automatique\n• Indicateurs de fraude → cohérence déclaration vs. photos',
        detailEn: '• Liability analysis → fault allocation\n• Repair estimate → amounts per item\n• IRSA convention → automatic application\n• Fraud indicators → declaration vs. photo consistency',
      },
      {
        icon: MessageSquare,
        title: '5. Ask IQ — Questions auto',
        titleEn: '5. Ask IQ — Auto questions',
        detail: 'Questions suggérées :\n\n→ "La franchise tous risques s\'applique-t-elle ici ?"\n→ "Le véhicule est-il réparable économiquement ?"\n→ "Quelle est la procédure de recours contre le tiers ?"',
        detailEn: 'Suggested questions:\n\n→ "Does the comprehensive deductible apply here?"\n→ "Is the vehicle economically repairable?"\n→ "What is the recovery procedure against the third party?"',
      },
      {
        icon: CheckCircle,
        title: '6. Décision sinistre auto',
        titleEn: '6. Auto claim decision',
        detail: 'Approuver / Ajuster / Refuser.\nEx: "Couvert CG Auto Art. 5.1, franchise 150€, recours tiers engagé."',
        detailEn: 'Approve / Adjust / Deny.\nEx: "Covered per Auto Terms Art. 5.1, €150 deductible, third-party recovery initiated."',
      },
    ],
  },
  {
    id: 'sante',
    label: 'Souscription Vie & Santé',
    labelEn: 'Life & Health Underwriting',
    icon: ClipboardList,
    color: brand.primary,
    summary: 'Antoine LEFEVRE, 48 ans, chef cuisinier — Complémentaire Santé Équilibre Plus — HTA contrôlée, ancien fumeur, père diabétique — 127 €/mois',
    summaryEn: 'Antoine LEFEVRE, 48 yo, chef — Complementary Health Equilibre Plus — Controlled hypertension, ex-smoker, father diabetic — €127/mo',
    demoPdf: `${DEMO_DIR}/sante/souscription-sante-lefevre.pdf`,
    steps: [
      {
        icon: ClipboardList,
        title: '1. Sélectionner "Souscription Vie & Santé"',
        titleEn: '1. Select "Life & Health Underwriting"',
        detail: 'Sélecteur de persona en haut → groupe "Souscription" → "Souscription Vie & Santé" (pictogramme liste).',
        detailEn: 'Top persona selector → "Underwriting" group → "Life & Health Underwriting" (clipboard/list line icon).',
        tip: 'Le RAG cherche dans les polices de souscription + CG Santé indexées.',
        tipEn: 'RAG searches underwriting policies + the indexed Health terms.',
      },
      {
        icon: Upload,
        title: '2. Uploader le dossier de souscription',
        titleEn: '2. Upload underwriting file',
        detail: '• souscription-sante-lefevre.pdf (email client + questionnaire de santé)\n• Pièces médicales mentionnées dans le PDF : ordonnance HTA, résultats d\'analyses, attestation SS, RIB\n\nUtiliser "Nouveau dossier" ou glisser-déposer le PDF. Activer "Document volumineux" seulement pour les dossiers très longs.',
        detailEn: '• souscription-sante-lefevre.pdf (client email + health questionnaire)\n• Medical attachments listed in the PDF: hypertension prescription, lab results, health coverage certificate, bank details\n\nUse "New Application" or drag and drop the PDF. Enable "Large document" only for very long files.',
        tip: `Le PDF est dans ${DEMO_DIR}/sante/.`,
        tipEn: `PDF is in ${DEMO_DIR}/sante/.`,
      },
      {
        icon: FileText,
        title: '3. Observer le traitement IA (2-3 min)',
        titleEn: '3. Watch AI processing (2-3 min)',
        detail: '① Extraction → champs du questionnaire santé extraits automatiquement\n② Analyse LLM → facteurs de risque détectés :\n   • HTA sous traitement (Amlodipine)\n   • Ancien fumeur (15 PA, arrêt 2021)\n   • IMC 27.2 (surpoids léger)\n   • ATCD paternel diabète type 2\n③ RAG → Conditions Complémentaire Santé',
        detailEn: '① Extraction engine → health questionnaire fields auto-extracted\n② LLM analysis → detected risk factors:\n   • Hypertension on medication (Amlodipine)\n   • Ex-smoker (15 pack-years, quit 2021)\n   • BMI 27.2 (mild overweight)\n   • Paternal history of type 2 diabetes\n③ RAG → Complementary Health terms',
      },
      {
        icon: Search,
        title: '4. Résultats de souscription',
        titleEn: '4. Underwriting results',
        detail: '• Résumé patient → Profil de risque complet\n• Chronologie → Historique médical structuré\n• Body System Map → Vue anatomique des pathologies\n• Source Pages → Questionnaire original avec citations',
        detailEn: '• Patient Summary → Full risk profile\n• Timeline → Structured medical history\n• Body System Map → Anatomical pathology view\n• Source Pages → Original questionnaire with citations',
        tip: 'Cliquer sur une carte Body System pour le deep dive avec sources.',
        tipEn: 'Click a Body System card for deep dive with sources.',
      },
      {
        icon: MessageSquare,
        title: '5. Ask IQ — Questions de souscription',
        titleEn: '5. Ask IQ — Underwriting questions',
        detail: 'Questions suggérées :\n\n→ "Quel est le niveau de risque cardiovasculaire de ce candidat ?"\n→ "L\'HTA sous traitement est-elle un motif de surprime ?"\n→ "Les ATCD familiaux de diabète impactent-ils la souscription ?"\n→ "Quelle formule recommanderiez-vous pour ce profil ?"',
        detailEn: 'Suggested questions:\n\n→ "What is this applicant\'s cardiovascular risk level?"\n→ "Is treated hypertension a surcharge factor?"\n→ "Does family history of diabetes impact underwriting?"\n→ "Which formula would you recommend for this profile?"',
      },
      {
        icon: CheckCircle,
        title: '6. Décision de souscription',
        titleEn: '6. Underwriting decision',
        detail: 'Le souscripteur peut :\n• Accepter en standard (aucune surprime)\n• Accepter avec surprime (ex: +15% pour HTA)\n• Demander examen complémentaire\n• Refuser (exclusion)\n\nNotes : "Accepté avec surprime 10% — HTA contrôlée, risque modéré."',
        detailEn: 'The underwriter can:\n• Accept at standard rate\n• Accept with surcharge (e.g., +15% for hypertension)\n• Request additional exam\n• Decline\n\nNotes: "Accepted with 10% surcharge — controlled hypertension, moderate risk."',
      },
    ],
  },
  {
    id: 'sante-sinistre',
    label: 'Sinistres Santé',
    labelEn: 'Health Claims',
    icon: Stethoscope,
    color: '#059669',
    summary: 'Demande dentaire urgente — consultation, radio, extraction + implant — devis 2 800 € / reste à charge estimé 1 900 €',
    summaryEn: 'Urgent dental request — consultation, X-ray, extraction + implant — €2,800 estimate / €1,900 estimated out-of-pocket',
    demoPdf: `${DEMO_DIR}/dental/`,
    steps: [
      {
        icon: Stethoscope,
        title: '1. Sélectionner "Sinistres Santé"',
        titleEn: '1. Select "Health Claims"',
        detail: 'Sélecteur de persona en haut → groupe "Sinistres" → "Sinistres Santé" (pictogramme stéthoscope).',
        detailEn: 'Top persona selector → "Claims" group → "Health Claims" (stethoscope line icon).',
        tip: 'Le RAG cherche dans la Complémentaire Santé indexée.',
        tipEn: 'RAG searches the indexed Complementary Health policy.',
      },
      {
        icon: Upload,
        title: '2. Uploader les justificatifs',
        titleEn: '2. Upload supporting documents',
        detail: `• thread4-01-client-dentaire.pdf (demande client)\n• thread4-02-${brand.key}-reponse-dentaire.pdf (réponse assureur)\n\nUtiliser "Nouveau dossier" ou glisser-déposer les PDF.`,
        detailEn: `• thread4-01-client-dentaire.pdf (client request)\n• thread4-02-${brand.key}-reponse-dentaire.pdf (insurer response)\n\nUse "New Application" or drag and drop the PDFs.`,
      },
      {
        icon: FileText,
        title: '3. Traitement IA',
        titleEn: '3. AI processing',
        detail: '① Extraction → extrait urgence, actes demandés, devis et identifiants adhérent\n② Analyse santé dédiée → couverture selon la formule souscrite\n③ Calcul → reste à charge après Sécu + complémentaire',
        detailEn: '① Extraction engine → extracts urgency, requested procedures, estimate and member identifiers\n② Dedicated health-claims analysis → coverage per subscribed plan\n③ Calculation → out-of-pocket after Social Security + complementary',
      },
      {
        icon: Search,
        title: '4. Résultats de remboursement',
        titleEn: '4. Reimbursement results',
        detail: '• Tableau des actes → Montants Sécu vs. complémentaire\n• Exclusions identifiées → Dépassements d\'honoraires, délais de carence\n• Citations polices → Articles des CG Santé applicables',
        detailEn: '• Procedure table → Social Security vs. complementary amounts\n• Exclusions identified → Fee overruns, waiting periods\n• Policy citations → Applicable Health Terms articles',
      },
      {
        icon: MessageSquare,
        title: '5. Ask IQ — Questions remboursement',
        titleEn: '5. Ask IQ — Reimbursement questions',
        detail: 'Questions suggérées :\n\n→ "Ce dépassement d\'honoraires est-il couvert ?"\n→ "Quel est le plafond annuel optique/dentaire ?"\n→ "Le délai de carence est-il expiré ?"',
        detailEn: 'Suggested questions:\n\n→ "Is this fee overrun covered?"\n→ "What is the annual optical/dental cap?"\n→ "Has the waiting period expired?"',
      },
      {
        icon: CheckCircle,
        title: '6. Décision de remboursement',
        titleEn: '6. Reimbursement decision',
        detail: 'Valider le remboursement calculé ou ajuster.\nEx: "Remboursé à 100% BR, dépassement honoraires exclu (Art. 4.3)."',
        detailEn: 'Validate calculated reimbursement or adjust.\nEx: "Reimbursed at 100% BR, fee overrun excluded (Art. 4.3)."',
      },
    ],
  },
  {
    id: 'hypothecaire',
    label: 'Souscription Hypothécaire',
    labelEn: 'Mortgage Underwriting',
    icon: Home,
    color: '#059669',
    summary: 'Dossier primo-accédant — Demande de prêt + compromis de vente + avis d\'imposition\nDossier app-mtg-004',
    summaryEn: 'First-time buyer file — Loan application + sale agreement + tax notice\nFile app-mtg-004',
    demoPdf: `${DEMO_DIR}/mortgage/souscription-hypothecaire/primo-accedant/app-mtg-004/`,
    steps: [
      {
        icon: Home,
        title: '1. Sélectionner "Souscription Hypothécaire"',
        titleEn: '1. Select "Mortgage Underwriting"',
        detail: 'Sélecteur de persona en haut → groupe "Souscription" → "Souscription Hypothécaire" (pictogramme maison).',
        detailEn: 'Top persona selector → "Underwriting" group → "Mortgage Underwriting" (home line icon).',
        tip: 'Interface spécifique avec chat hypothécaire intégré.',
        tipEn: 'Dedicated interface with integrated mortgage chat.',
      },
      {
        icon: Upload,
        title: '2. Uploader le dossier complet',
        titleEn: '2. Upload complete file',
        detail: '• demande_pret_immobilier.pdf (formulaire de demande)\n• compromis_vente.pdf (compromis signé)\n• avis_imposition_2024.pdf (revenus fiscaux)\n\nUtiliser "Nouveau dossier" ou glisser-déposer les PDF.',
        detailEn: '• demande_pret_immobilier.pdf (loan application form)\n• compromis_vente.pdf (signed sale agreement)\n• avis_imposition_2024.pdf (tax return)\n\nUse "New Application" or drag and drop the PDFs.',
        tip: `Fichiers dans ${DEMO_DIR}/mortgage/souscription-hypothecaire/primo-accedant/app-mtg-004/.`,
        tipEn: `Files in ${DEMO_DIR}/mortgage/souscription-hypothecaire/primo-accedant/app-mtg-004/.`,
      },
      {
        icon: FileText,
        title: '3. Analyse IA du dossier',
        titleEn: '3. AI file analysis',
        detail: '① Extraction → revenus, charges, montant emprunté, valeur du bien\n② Analyse hypothécaire → taux d\'endettement, ratio LTV, apport personnel\n③ Éligibilité → vérification HCSF / PTZ / pièces manquantes',
        detailEn: '① Extraction engine → income, expenses, loan amount, property value\n② Mortgage analysis → debt-to-income ratio, LTV ratio, down payment\n③ Eligibility → HCSF / PTZ / missing-document checks',
      },
      {
        icon: Search,
        title: '4. Résultats d\'éligibilité',
        titleEn: '4. Eligibility results',
        detail: '• Tableau synthétique → revenus, charges, capacité d\'emprunt\n• Ratio LTV → comparaison avec les seuils de risque\n• Taux d\'endettement → conformité règle des 35%\n• Pièces manquantes → liste des documents à fournir',
        detailEn: '• Summary table → income, expenses, borrowing capacity\n• LTV ratio → comparison with risk thresholds\n• Debt-to-income → 35% rule compliance\n• Missing documents → list of required paperwork',
      },
      {
        icon: MessageSquare,
        title: '5. Chat hypothécaire',
        titleEn: '5. Mortgage chat',
        detail: 'Chat hypothécaire intégré dans la vue "Souscription Hypothécaire" :\n\n→ "Le dossier est-il éligible au PTZ ?"\n→ "Quel est le taux d\'endettement calculé ?"\n→ "Quelles pièces manquent pour finaliser ?"',
        detailEn: 'Mortgage chat integrated in the "Mortgage Underwriting" view:\n\n→ "Is the file eligible for PTZ?"\n→ "What is the calculated debt-to-income ratio?"\n→ "What documents are missing to finalize?"',
      },
      {
        icon: CheckCircle,
        title: '6. Décision hypothécaire',
        titleEn: '6. Mortgage decision',
        detail: 'Accepter / Demander compléments / Refuser.\nEx: "Éligible PTZ, taux endettement 28%, RAS. Accord sous réserve attestation employeur."',
        detailEn: 'Accept / Request supplements / Deny.\nEx: "PTZ eligible, 28% DTI, all clear. Approved pending employer certificate."',
      },
    ],
  },
  {
    id: 'client360',
    label: 'Client 360',
    labelEn: 'Customer 360',
    icon: Users,
    color: '#0ea5e9',
    summary: `Vue agrégée d'un client ${brand.companyName} — tous contrats, sinistres, communications\nClients fictifs pré-chargés, IDs conservés tels qu'ils existent en base (ex: ${CUSTOMER_ID('001')})`,
    summaryEn: `Aggregated view of a ${brand.companyName} customer — all policies, claims, communications\nPre-loaded fictional customers, IDs preserved as they exist in storage (e.g., ${CUSTOMER_ID('001')})`,
    demoPdf: '',
    steps: [
      {
        icon: Users,
        title: '1. Sélectionner "Client 360"',
        titleEn: '1. Select "Customer 360"',
        detail: 'Barre supérieure → bouton "Client 360" (pictogramme utilisateurs). Ce n\'est pas une option du sélecteur de persona.',
        detailEn: 'Top bar → "Customer 360" button (users line icon). It is not an option in the persona selector.',
        tip: 'Pas d\'upload nécessaire — les clients sont pré-chargés.',
        tipEn: 'No upload needed — customers are pre-loaded.',
      },
      {
        icon: Search,
        title: '2. Rechercher un client',
        titleEn: '2. Search for a customer',
        detail: `Barre de recherche → taper un nom, email ou ID client (ex: "Dupont", "${CUSTOMER_ID('005')}").\nLe profil s'affiche avec toutes les informations agrégées.`,
        detailEn: `Search bar → type a name, email or customer ID (e.g., "Dupont", "${CUSTOMER_ID('005')}").\nProfile displays with all aggregated information.`,
      },
      {
        icon: FileText,
        title: '3. Vue d\'ensemble du client',
        titleEn: '3. Customer overview',
        detail: '• Informations personnelles → Nom, adresse, téléphone, email\n• Contrats actifs → Liste des polices (auto, habitation, santé)\n• Historique sinistres → Tous les dossiers traités\n• Score fidélité → Ancienneté, multi-équipement',
        detailEn: '• Personal information → Name, address, phone, email\n• Active policies → Policy list (auto, home, health)\n• Claims history → All processed files\n• Loyalty score → Tenure, multi-product',
      },
      {
        icon: ClipboardList,
        title: '4. Dossiers affiliés',
        titleEn: '4. Affiliated files',
        detail: 'Les dossiers traités dans les autres personas sont automatiquement\nrattachés au profil client (par nom d\'assuré).\n\nCliquer sur un dossier → ouvre le détail dans la persona d\'origine.',
        detailEn: 'Files processed in other personas are automatically\nlinked to the customer profile (by insured name).\n\nClick a file → opens detail in the original persona.',
      },
      {
        icon: MessageSquare,
        title: '5. Ask IQ — Questions client',
        titleEn: '5. Ask IQ — Customer questions',
        detail: 'Questions suggérées :\n\n→ "Combien de sinistres ce client a-t-il déclarés ?"\n→ "Quelles opportunités de cross-sell pour ce profil ?"\n→ "Y a-t-il des anomalies dans l\'historique ?"',
        detailEn: 'Suggested questions:\n\n→ "How many claims has this customer filed?"\n→ "What cross-sell opportunities for this profile?"\n→ "Are there anomalies in the history?"',
      },
      {
        icon: CheckCircle,
        title: '6. Actions commerciales',
        titleEn: '6. Commercial actions',
        detail: 'Depuis le profil client :\n• Envoyer un devis multi-équipement\n• Planifier un rappel\n• Générer un rapport de fidélisation',
        detailEn: 'From the customer profile:\n• Send a multi-product quote\n• Schedule a callback\n• Generate a loyalty report',
      },
    ],
  },
];

const ALL_STEPS_ICONS = [CloudRain, Upload, FileText, Search, MessageSquare, CheckCircle, ClipboardList, Stethoscope, ImageIcon, Car, Home, Shield, Users];

export default function DemoGuideModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [expandedStep, setExpandedStep] = useState<number | null>(0);
  const locale = useLocale();
  const isFr = locale === 'fr';
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const scenario = SCENARIOS[scenarioIdx];

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg transition-colors"
        style={{ color: brand.primary, backgroundColor: `${brand.primary}0D`, borderColor: `${brand.primary}33` }}
        title={isFr ? 'Guide de démonstration' : 'Demo guide'}
      >
        <HelpCircle className="w-4 h-4" />
        <span>{isFr ? 'Démo' : 'Demo'}</span>
      </button>
    );
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 z-50" onClick={() => setIsOpen(false)} />

      {/* Modal */}
      <div className="fixed top-1/2 left-1/2 z-50 flex max-h-[92vh] w-[96vw] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4 border-b border-slate-200 rounded-t-2xl"
          style={{ background: `linear-gradient(90deg, ${brand.gradientStart}, ${brand.gradientEnd})` }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 shadow-sm">
              <img src={brand.favicon} alt="" className="h-9 w-9 rounded-lg" />
              <span className="text-sm font-bold tracking-tight" style={{ color: brand.primary }}>
                {brand.name}
              </span>
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-white">
                {isFr ? 'Guide de Démonstration' : 'Demo Guide'}
              </h2>
              <p className="truncate text-sm font-medium text-white">
                {isFr
                  ? `Démo pour ${brand.companyName} — ${scenario.label}`
                  : `Demo for ${brand.companyName} — ${scenario.labelEn}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 text-white/70 hover:text-white rounded-lg hover:bg-white/15"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scenario Tabs */}
        <div className="flex flex-wrap gap-1.5 border-b border-slate-200 bg-slate-50/50 px-4 pt-3">
          {SCENARIOS.map((s, i) => {
            const Icon = s.icon;
            const active = scenarioIdx === i;
            return (
              <button
                key={s.id}
                onClick={() => { setScenarioIdx(i); setExpandedStep(0); }}
                className={clsx(
                  'flex items-center gap-2 rounded-t-xl border-b-2 px-4 py-3 text-sm font-semibold whitespace-nowrap transition-colors',
                  active
                    ? 'bg-white border-current shadow-sm'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-white/60'
                )}
                style={active ? { color: s.color } : {}}
              >
                <Icon className="h-[18px] w-[18px]" />
                {isFr ? s.label : s.labelEn}
              </button>
            );
          })}
        </div>

        {/* Scenario summary */}
        <div className="px-6 py-3 bg-amber-50 border-b border-amber-100 text-sm">
          <p className="font-medium text-amber-800">
            {isFr ? 'Scénario :' : 'Scenario:'}
          </p>
          <p className="text-amber-700">
            {isFr ? scenario.summary : scenario.summaryEn}
          </p>
        </div>

        {/* Steps */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {scenario.steps.map((step, i) => {
            const isExpanded = expandedStep === i;
            const Icon = step.icon;
            return (
              <div key={i} className="border border-slate-200 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedStep(isExpanded ? null : i)}
                  className={clsx(
                    'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
                    isExpanded ? '' : 'bg-white hover:bg-slate-50'
                  )}
                  style={isExpanded ? { backgroundColor: `${brand.primary}0D` } : undefined}
                >
                  <Icon
                    className={clsx('w-5 h-5 flex-shrink-0', isExpanded ? '' : 'text-slate-400')}
                    style={isExpanded ? { color: brand.primary } : undefined}
                  />
                  <span
                    className={clsx('text-sm font-medium flex-1', isExpanded ? '' : 'text-slate-700')}
                    style={isExpanded ? { color: brand.primary } : undefined}
                  >
                    {isFr ? step.title : step.titleEn}
                  </span>
                  {isExpanded
                    ? <ChevronDown className="w-4 h-4" style={{ color: brand.secondary }} />
                    : <ChevronRight className="w-4 h-4 text-slate-400" />}
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 pt-1" style={{ backgroundColor: `${brand.primary}08` }}>
                    <p className="text-sm text-slate-600 whitespace-pre-line">
                      {isFr ? step.detail : step.detailEn}
                    </p>
                    {(isFr ? step.tip : step.tipEn) && (
                      <p className="mt-2 text-xs text-amber-700 bg-amber-50 px-3 py-2 rounded-lg border border-amber-100">
                        💡 {isFr ? step.tip : step.tipEn}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex min-h-[88px] items-center justify-between gap-5 rounded-b-2xl border-t border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex flex-shrink-0 items-center gap-3">
            <div className="flex h-14 items-center rounded-xl bg-white px-4 shadow-sm ring-1 ring-slate-200">
              <img src="/microsoft-logo-gray.avif" alt="Microsoft" className="h-10 w-auto opacity-100" />
            </div>
            <span className="text-lg font-bold text-slate-700">×</span>
            <div className="flex h-14 items-center rounded-xl bg-white px-4 shadow-sm ring-1 ring-slate-200">
              <img src={brand.logo} alt={brand.logoAlt} className="h-11 max-w-[190px] w-auto object-contain opacity-100" />
            </div>
          </div>
          <p className="hidden flex-1 text-center text-xs font-medium text-slate-700 sm:block">
            {isFr
              ? `${scenario.demoPdf ? 'PDF' : 'Démo'} : ${scenario.demoPdf || 'Client 360 préchargé'}`
              : `${scenario.demoPdf ? 'PDF' : 'Demo'}: ${scenario.demoPdf || 'Preloaded Client 360'}`}
          </p>
          <button
            onClick={() => setIsOpen(false)}
            className="flex-shrink-0 rounded-lg px-5 py-2.5 text-sm font-semibold text-white"
            style={{ backgroundColor: brand.primary }}
          >
            {isFr ? 'Fermer' : 'Close'}
          </button>
        </div>
      </div>
    </>
  );
}
