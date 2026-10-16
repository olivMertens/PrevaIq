/**
 * Brand configuration — determined at build time via NEXT_PUBLIC_BRAND_NAME (default: PrevaIQ).
 */

interface BrandConfig {
  name: string;        // e.g. "PrevaIQ"
  prefix: string;      // e.g. "Preva"
  key: string;
  companyName: string;
  logo: string;        // public/ path
  logoAlt: string;
  favicon: string;
  primary: string;     // hex
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
    logo: '/prevaiq-logo.svg',
    logoAlt: 'PrevaIQ',
    favicon: '/favicon-prevaiq.svg',
    primary: '#17395C',
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

/** True when an action-history system tag refers to the workbench itself (e.g. "PrevaIQ"). */
export function isWorkbenchSystem(system: string): boolean {
  return system === brand.name || /IQ$/.test(system);
}
