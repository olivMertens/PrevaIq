'use client';

import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { useTranslations } from 'next-intl';

type ProcessingStep = 'idle' | 'uploading' | 'extracting' | 'analyzing' | 'complete' | 'error';

interface ProcessingBannerProps {
  step: ProcessingStep;
  message: string;
  appId: string | null;
  onSelectApp: (appId: string) => void;
  onDismiss: () => void;
}

export default function ProcessingBanner({ step, message, appId, onSelectApp, onDismiss }: ProcessingBannerProps) {
  const t = useTranslations('dashboard');

  if (step === 'idle') return null;

  const stepLabels = [t('stepUpload'), t('stepExtract'), t('stepAnalyze'), t('stepDone')];
  const steps: ProcessingStep[] = ['uploading', 'extracting', 'analyzing', 'complete'];
  const displayMessage = message?.trim() || t('processingFailed');

  return (
    <div className="max-w-7xl 2xl:max-w-[96rem] mx-auto px-6 lg:px-8 pt-4">
      <div className={clsx(
        'rounded-xl border p-4 flex items-center gap-4 transition-all',
        step === 'error' ? 'bg-rose-50 border-rose-200' :
        step === 'complete' ? 'bg-emerald-50 border-emerald-200' : 'bg-sky-50 border-sky-200'
      )}>
        <div className={clsx(
          'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0',
          step === 'error' ? 'bg-rose-100' : step === 'complete' ? 'bg-emerald-100' : 'bg-sky-100'
        )}>
          {step === 'error' ? <AlertCircle className="w-5 h-5 text-rose-600" /> :
           step === 'complete' ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> :
           <Loader2 className="w-5 h-5 text-sky-600 animate-spin" />}
        </div>

        <div className="flex-1 min-w-0">
          {step === 'error' ? (
            <p className="text-xs font-semibold uppercase tracking-wide text-rose-700 mb-1">
              {t('processingFailedTitle')}
            </p>
          ) : (
            <div className="flex items-center gap-3 mb-1">
              {steps.map((s, i) => {
                const stepIndex = steps.indexOf(step as typeof steps[number]);
                const isDone = stepIndex > i || step === 'complete';
                const isCurrent = step === s;
                return (
                  <div key={s} className="flex items-center gap-1.5">
                    {i > 0 && <div className={clsx('w-6 h-px', isDone || isCurrent ? 'bg-sky-400' : 'bg-slate-200')} />}
                    <span className={clsx(
                      'text-xs font-medium',
                      isCurrent ? 'text-sky-700' : isDone ? 'text-emerald-600' : 'text-slate-400'
                    )}>{stepLabels[i]}</span>
                  </div>
                );
              })}
            </div>
          )}
          <p className={clsx(
            'text-sm font-medium',
            step === 'error' ? 'whitespace-pre-wrap break-words' : 'truncate',
            step === 'error' ? 'text-rose-700' : step === 'complete' ? 'text-emerald-700' : 'text-sky-700'
          )}>{displayMessage}</p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {appId && ['extracting', 'analyzing', 'complete'].includes(step) && (
            <button onClick={() => onSelectApp(appId)}
              className="px-3 py-1.5 text-xs font-medium bg-white border border-sky-200 text-sky-700 rounded-lg hover:bg-sky-50 transition-colors">
              {t('open')}
            </button>
          )}
          {(step === 'error' || step === 'complete') && (
            <button onClick={onDismiss} className="p-1.5 text-slate-400 hover:text-slate-600 transition-colors" title={t('dismiss')}>✕</button>
          )}
        </div>
      </div>
    </div>
  );
}
