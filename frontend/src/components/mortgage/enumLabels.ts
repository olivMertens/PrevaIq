type Translate = (key: string) => string;

const EMPLOYMENT_KEYS: Record<string, string> = {
  permanent_full_time: 'employment.permanentFullTime',
  permanent_part_time: 'employment.permanentPartTime',
  contract: 'employment.contract',
  self_employed: 'employment.selfEmployed',
  commission: 'employment.commission',
  retired: 'employment.retired',
  unemployed: 'employment.unemployed',
  other: 'employment.other',
  cdi: 'employment.permanentFullTime',
  cdd: 'employment.contract',
  fonctionnaire: 'employment.civilServant',
  profession_liberale: 'employment.professional',
  interim: 'employment.temporary',
};

const PROPERTY_TYPE_KEYS: Record<string, string> = {
  single_family_detached: 'property.detached',
  semi_detached: 'property.semiDetached',
  townhouse: 'property.townhouse',
  condominium: 'property.condominium',
  duplex: 'property.duplex',
  triplex: 'property.triplex',
  fourplex: 'property.fourplex',
  mobile_home: 'property.mobileHome',
  modular_home: 'property.modularHome',
  mixed_use: 'property.mixedUse',
  maison_individuelle: 'property.detached',
  appartement: 'property.apartment',
  immeuble_de_rapport: 'property.incomeProperty',
};

const OCCUPANCY_KEYS: Record<string, string> = {
  owner_occupied: 'occupancy.primary',
  second_home: 'occupancy.secondary',
  investment_rental: 'occupancy.rental',
};

const DOWN_PAYMENT_SOURCE_KEYS: Record<string, string> = {
  savings: 'downPayment.savings',
  gift: 'downPayment.gift',
  rrsp_hbp: 'downPayment.savingsPlan',
  pel: 'downPayment.pel',
  cel: 'downPayment.cel',
  donation: 'downPayment.familyGift',
  vente_bien: 'downPayment.propertySale',
  pret_familial: 'downPayment.familyLoan',
};

const RATE_TYPE_KEYS: Record<string, string> = {
  variable: 'rate.variable',
  fixed_1_year: 'rate.fixed1',
  fixed_2_year: 'rate.fixed2',
  fixed_3_year: 'rate.fixed3',
  fixed_4_year: 'rate.fixed4',
  fixed_5_year: 'rate.fixed5',
  fixed_7_year: 'rate.fixed7',
  fixed_10_year: 'rate.fixed10',
  taux_fixe: 'rate.fixed',
  taux_variable: 'rate.variable',
};

const PRODUCT_TYPE_KEYS: Record<string, string> = {
  conventional: 'product.amortizing',
  high_ratio: 'product.highLtv',
  cmhc_insured: 'product.amortizing',
  genworth_insured: 'product.amortizing',
  canada_guaranty_insured: 'product.amortizing',
  refinance: 'product.refinance',
  renewal: 'product.renewal',
  switch: 'product.switch',
  pret_amortissable: 'product.amortizing',
  pret_relais: 'product.bridge',
  pret_in_fine: 'product.interestOnly',
  pret_taux_zero: 'product.zeroRate',
};

function lookup(map: Record<string, string>, value: unknown, t: Translate): string {
  if (value === null || value === undefined || value === '') return '';
  const key = map[String(value).toLowerCase()];
  return key ? t(`enums.${key}`) : String(value);
}

export const formatEmploymentType = (v: unknown, t: Translate) => lookup(EMPLOYMENT_KEYS, v, t);
export const formatPropertyType = (v: unknown, t: Translate) => lookup(PROPERTY_TYPE_KEYS, v, t);
export const formatOccupancy = (v: unknown, t: Translate) => lookup(OCCUPANCY_KEYS, v, t);
export const formatDownPaymentSource = (v: unknown, t: Translate) => lookup(DOWN_PAYMENT_SOURCE_KEYS, v, t);
export const formatRateType = (v: unknown, t: Translate) => lookup(RATE_TYPE_KEYS, v, t);
export const formatProductType = (v: unknown, t: Translate) => lookup(PRODUCT_TYPE_KEYS, v, t);
