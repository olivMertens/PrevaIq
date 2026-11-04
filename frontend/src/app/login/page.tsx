'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useTranslations } from 'next-intl';
import BrandMark from '@/components/BrandMark';
import { useLoginTheme } from '@/components/auth/LoginShell';
import styles from '@/components/auth/login.module.css';
import LoginHero from '@/components/auth/LoginHero';
import EntraButton from '@/components/auth/EntraButton';
import { mailtoHref, useAuthProviders } from '@/components/auth/useAuthProviders';

const CALLBACK_ERRORS: Record<string, 'errorState' | 'errorEntra' | 'errorCapacity'> = {
  state: 'errorState',
  entra: 'errorEntra',
  capacity: 'errorCapacity',
};

export default function LoginPage() {
  const t = useTranslations('auth');
  const theme = useLoginTheme();
  const { entraEnabled, localAuthEnabled, loaded, requestEmail } = useAuthProviders();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [capacityFull, setCapacityFull] = useState(false);
  const [alreadyConnected, setAlreadyConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const key = CALLBACK_ERRORS[new URLSearchParams(window.location.search).get('error') || ''];
    if (key) setError(t(key));
  }, [t]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setCapacityFull(false);
    setAlreadyConnected(false);
    setLoading(true);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      if (res.ok) {
        // Hard redirect to force full page reload so TopNav picks up session
        window.location.href = '/';
        return;
      } else if (res.status === 409) {
        setAlreadyConnected(true);
      } else if (res.status === 429) {
        setCapacityFull(true);
      } else {
        const data = await res.json();
        setError(data.error || t('error'));
      }
    } catch {
      setError(t('error'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.layout}>
      <LoginHero />
      <section className={styles.card} aria-labelledby="login-title">
        <div className={styles.cardBrand}><BrandMark surface={theme} /></div>
        <h2 id="login-title" className={styles.title}>{t('signIn')}</h2>

        {entraEnabled && (
          <div className={styles.sso}>
            <EntraButton label={t('entraButton')} />
            <p className={styles.hint}>{t('entraHint')}</p>
            {localAuthEnabled && <div className={styles.divider}>
              <span />
              {t('or')} · {t('demoAccount')}
              <span />
            </div>}
          </div>
        )}

        {loaded && !entraEnabled && !localAuthEnabled && (
          <div role="alert" className={styles.error}>
            {t('unavailable')}
          </div>
        )}

        {(entraEnabled || localAuthEnabled) && (
          <p className={styles.hint}>{t('demoAccessNotice')}</p>
        )}

        <div aria-live="polite" className={styles.feedback}>
          {alreadyConnected && (
            <div className={styles.warning}>
              {t('alreadyConnected')}
            </div>
          )}

          {capacityFull && (
            <div className={styles.error}>
              {t('capacityFull')}
            </div>
          )}

          {error && !capacityFull && !alreadyConnected && (
            <div className={styles.error}>
              {error}
            </div>
          )}
        </div>

        {localAuthEnabled && <form onSubmit={handleSubmit} className={styles.form}>
          <div>
            <label htmlFor="username" className={styles.label}>
              {t('username')}
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className={styles.input}
              placeholder={t('username')}
            />
          </div>

          <div>
            <label htmlFor="password" className={styles.label}>
              {t('password')}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className={styles.input}
              placeholder={t('password')}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className={styles.button}
          >
            {loading ? t('loggingIn') : t('loginButton')}
          </button>
        </form>}

        <div className={styles.request}>
          <h3>{t('requestTitle')}</h3>
          <p>{t('requestLead')}</p>
          {requestEmail && (
            <a
              href={mailtoHref(requestEmail, t('requestMailSubject'), t('requestMailBody'))}
              className={`${styles.button} ${styles.secondary}`}
            >
              {t('requestButton')}
            </a>
          )}
          {requestEmail && (
            <p className={styles.contact}>
              {t('contactUs')}:{' '}
              <a href={`mailto:${requestEmail}`} className={styles.link}>
                {requestEmail}
              </a>
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
