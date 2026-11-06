'use client';

import Image from 'next/image';
import { useContext } from 'react';
import { brand } from '@/lib/brand';
import { ThemeContext } from '@/lib/ThemeProvider';

interface BrandMarkProps {
  compact?: boolean;
  surface?: 'light' | 'dark';
}

/** Official FDR wordmark, chosen for the actual surface rather than recolored with CSS. */
export default function BrandMark({ compact = false, surface }: BrandMarkProps) {
  const theme = useContext(ThemeContext)?.theme ?? 'light';
  const actualSurface = surface ?? theme;
  return (
    <Image
      src={actualSurface === 'dark' ? brand.logoDark : brand.logo}
      alt={brand.logoAlt}
      width={859}
      height={254}
      loading="eager"
      unoptimized
      className={compact ? 'h-9 w-auto max-w-[160px] object-contain' : 'h-11 w-auto max-w-[180px] object-contain'}
    />
  );
}
