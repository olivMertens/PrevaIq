import { brand } from '@/lib/brand';

/**
 * Brand logo. PrevaIQ ships a full product wordmark, so it is shown alone;
 * other brands pair their logo with the generic "IQ" badge.
 */
export default function BrandMark({ compact = false }: { compact?: boolean }) {
  if (brand.key === 'prevaiq') {
    return (
      <img
        src={brand.logo}
        alt={brand.logoAlt}
        className={compact ? 'h-9 w-auto max-w-[160px] object-contain' : 'h-11 w-auto max-w-[180px] object-contain'}
      />
    );
  }
  const gradientId = compact ? 'brandmark-grad-compact' : 'brandmark-grad';
  return (
    <>
      <img src={brand.logo} alt={brand.logoAlt} className="h-10 w-auto max-w-[150px] object-contain" />
      <span className="select-none text-slate-300 font-light">|</span>
      <svg width="36" height="36" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="flex-shrink-0">
        <rect width="32" height="32" rx="8" fill={`url(#${gradientId})`}/>
        <text x="16" y="22" textAnchor="middle" fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="16" fill="white">IQ</text>
        <circle cx="26" cy="6" r="3" fill={brand.dotColor} opacity="0.9"/>
        <defs><linearGradient id={gradientId} x1="0" y1="0" x2="32" y2="32"><stop offset="0%" stopColor={brand.gradientStart}/><stop offset="100%" stopColor={brand.gradientEnd}/></linearGradient></defs>
      </svg>
      <span className="text-xl font-bold tracking-tight">
        <span className="text-slate-900">{brand.prefix}</span><span style={{ color: brand.primary }}>IQ</span>
      </span>
    </>
  );
}
