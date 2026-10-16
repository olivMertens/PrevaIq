/**
 * French display labels for mortgage enum values.
 *
 * Backend stores legacy Canadian enum strings for backwards-compat with
 * stored demo data, but the UI must display French labels (HCSF).
 */

const EMPLOYMENT_LABELS: Record<string, string> = {
  permanent_full_time: 'CDI',
  permanent_part_time: 'CDI temps partiel',
  contract: 'CDD',
  self_employed: 'Indépendant',
  commission: 'Commercial / commission',
  retired: 'Retraité',
  unemployed: 'Sans emploi',
  other: 'Autre',
  // direct French
  cdi: 'CDI',
  cdd: 'CDD',
  fonctionnaire: 'Fonctionnaire',
  profession_liberale: 'Profession libérale',
  interim: 'Intérim',
};

const PROPERTY_TYPE_LABELS: Record<string, string> = {
  single_family_detached: 'Maison individuelle',
  semi_detached: 'Maison jumelée',
  townhouse: 'Maison de ville',
  condominium: 'Appartement (copropriété)',
  duplex: 'Duplex',
  triplex: 'Triplex',
  fourplex: 'Immeuble 4 lots',
  mobile_home: 'Mobil-home',
  modular_home: 'Maison modulaire',
  mixed_use: 'Mixte',
  // direct French
  maison_individuelle: 'Maison individuelle',
  appartement: 'Appartement',
  immeuble_de_rapport: 'Immeuble de rapport',
};

const OCCUPANCY_LABELS: Record<string, string> = {
  owner_occupied: 'Résidence principale',
  second_home: 'Résidence secondaire',
  investment_rental: 'Investissement locatif',
};

const DOWN_PAYMENT_SOURCE_LABELS: Record<string, string> = {
  savings: 'Épargne personnelle',
  gift: 'Donation',
  rrsp_hbp: 'PEL / Plan épargne',
  pel: 'PEL',
  cel: 'CEL',
  donation: 'Donation familiale',
  vente_bien: 'Vente d’un bien',
  pret_familial: 'Prêt familial',
};

const RATE_TYPE_LABELS: Record<string, string> = {
  variable: 'Taux variable',
  fixed_1_year: 'Taux fixe 1 an',
  fixed_2_year: 'Taux fixe 2 ans',
  fixed_3_year: 'Taux fixe 3 ans',
  fixed_4_year: 'Taux fixe 4 ans',
  fixed_5_year: 'Taux fixe 5 ans',
  fixed_7_year: 'Taux fixe 7 ans',
  fixed_10_year: 'Taux fixe 10 ans',
  taux_fixe: 'Taux fixe',
  taux_variable: 'Taux variable',
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  conventional: 'Prêt amortissable',
  high_ratio: 'Prêt à fort LTV',
  cmhc_insured: 'Prêt amortissable',
  genworth_insured: 'Prêt amortissable',
  canada_guaranty_insured: 'Prêt amortissable',
  refinance: 'Rachat de crédit',
  renewal: 'Renouvellement',
  switch: 'Transfert',
  pret_amortissable: 'Prêt amortissable',
  pret_relais: 'Prêt relais',
  pret_in_fine: 'Prêt in fine',
  pret_taux_zero: 'Prêt à taux zéro (PTZ)',
};

function lookup(map: Record<string, string>, value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const key = String(value).toLowerCase();
  return map[key] || String(value);
}

export const formatEmploymentType = (v: unknown) => lookup(EMPLOYMENT_LABELS, v);
export const formatPropertyType = (v: unknown) => lookup(PROPERTY_TYPE_LABELS, v);
export const formatOccupancy = (v: unknown) => lookup(OCCUPANCY_LABELS, v);
export const formatDownPaymentSource = (v: unknown) => lookup(DOWN_PAYMENT_SOURCE_LABELS, v);
export const formatRateType = (v: unknown) => lookup(RATE_TYPE_LABELS, v);
export const formatProductType = (v: unknown) => lookup(PRODUCT_TYPE_LABELS, v);
