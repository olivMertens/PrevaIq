'use client';

import { useTranslations } from 'next-intl';
import { FileSearch, GitBranch, ShieldCheck } from 'lucide-react';
import styles from './login.module.css';
import BrandMark from '@/components/BrandMark';

const POINTS = [
  { key: 'splashPoint1', icon: FileSearch },
  { key: 'splashPoint2', icon: GitBranch },
  { key: 'splashPoint3', icon: ShieldCheck },
] as const;

/** Branded splash panel of the sign-in screen. */
export default function LoginHero() {
  const t = useTranslations('auth');
  return (
    <section className={styles.hero} aria-labelledby="login-hero-title">
      <div aria-hidden className={`${styles.glow} ${styles.glowTop}`} />
      <div aria-hidden className={`${styles.glow} ${styles.glowBottom}`} />
      <div className={styles.heroContent}>
        <div className={styles.heroBrand}><BrandMark compact surface="dark" /></div>
        <p className={styles.eyebrow}>{t('splashEyebrow')}</p>
        <h1 id="login-hero-title" className={styles.heroTitle}>{t('splashTitle')}</h1>
        <p className={styles.heroLead}>{t('splashLead')}</p>
      </div>
      <div className={`${styles.heroContent} ${styles.heroBottom}`}>
        <ul className={styles.points}>
          {POINTS.map(({ key, icon: Icon }) => (
            <li key={key} className={styles.point}>
              <span className={styles.pointIcon} aria-hidden>
                <Icon size={17} strokeWidth={1.8} />
              </span>
              {t(key)}
            </li>
          ))}
        </ul>
        <p className={styles.heroNote}><ShieldCheck size={15} aria-hidden />{t('splashFraudNotice')}</p>
      </div>
    </section>
  );
}
