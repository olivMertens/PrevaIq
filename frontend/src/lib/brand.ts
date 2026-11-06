/**
 * Brand configuration — determined at build time via NEXT_PUBLIC_BRAND_NAME (default: PrevaIQ).
 */

interface BrandConfig {
  name: string;        // e.g. "PrevaIQ"
  prefix: string;      // e.g. "Preva"
  key: string;
  companyName: string;
  logo: string;        // public/ path
  logoDark: string;
  icon: string;
  iconDark: string;
  logoAlt: string;
  favicon: string;
  primary: string;     // hex
  ink: string;
  secondary: string;
  accent: string;
  gradientStart: string;
  gradientEnd: string;
  dotColor: string;
  demoAssetsDir: string;
  customerIdPrefix: string;
  insurerPhone: string;
}

const brands: Record<string, BrandConfig> = {
  PrevaIQ: {
    name: 'PrevaIQ',
    prefix: 'Preva',
    key: 'prevaiq',
    companyName: 'PrevaIQ Assurance',
    logo: '/prevaiq-logo.png',
    logoDark: '/prevaiq-logo-dark.png',
    icon: '/prevaiq-icon.png',
    iconDark: '/prevaiq-icon-dark.png',
    logoAlt: 'PrevaIQ',
    favicon: '/favicon.svg',
    primary: '#17395C',
    ink: 'var(--app-brand-ink, #17395C)',
    secondary: '#2EC4B6',
    accent: '#0F2E4D',
    gradientStart: '#17395C',
    gradientEnd: '#0F2E4D',
    dotColor: '#2EC4B6',
    demoAssetsDir: 'assets/demo-prevaiq',
    customerIdPrefix: 'PRV',
    insurerPhone: '09 72 12 34 56',
  },
};

const brandKey = process.env.NEXT_PUBLIC_BRAND_NAME || 'PrevaIQ';
export const brand: BrandConfig = brands[brandKey] || brands.PrevaIQ;

/** Inline persona/demo accents stay legible on dark cards without recoloring assets. */
export function readableAccent(color: string): string {
  return `light-dark(${color}, color-mix(in srgb, ${color} 35%, white))`;
}

/** True when an action-history system tag refers to the workbench itself (e.g. "PrevaIQ"). */
export function isWorkbenchSystem(system: string): boolean {
  return system === brand.name || /IQ$/.test(system);
}
