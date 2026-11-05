'use client';

import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { AlertTriangle, Download, FileText, ImageIcon, Paperclip } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { getEmailPreview, type EmailAttachment, type EmailPreview } from '@/lib/api';
import MarkdownText from './claims/property/MarkdownText';

// E-mails already shown in this session: going back to one is instant.
const previews = new Map<string, EmailPreview>();

interface EmailViewProps {
  applicationId: string;
  fileName: string;
  /** Raw .eml, offered as a download when the e-mail cannot be read. */
  fileUrl: string;
  /** Opens an attachment that is also a file of the case. */
  onOpenFile: (fileName: string) => void;
}

function attachmentIcon(attachment: EmailAttachment) {
  if (attachment.content_type.startsWith('image/')) return ImageIcon;
  return attachment.content_type === 'application/pdf' ? FileText : Paperclip;
}

/** An e-mail as a mail client shows it: subject, sender and recipients, attachments, body. */
export default function EmailView({ applicationId, fileName, fileUrl, onOpenFile }: EmailViewProps) {
  const t = useTranslations('documentViewer');
  const locale = useLocale();
  const key = `${applicationId}/${fileName}`;
  const [email, setEmail] = useState<EmailPreview | null>(() => previews.get(key) ?? null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (previews.has(key)) return;
    let active = true;
    getEmailPreview(applicationId, fileName).then(
      (preview) => {
        previews.set(key, preview);
        if (active) setEmail(preview);
      },
      () => {
        if (active) setFailed(true);
      },
    );
    return () => {
      active = false;
    };
  }, [applicationId, fileName, key]);

  if (failed) {
    return (
      <div className="mt-8 max-w-sm rounded-lg bg-white p-8 text-center shadow">
        <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden />
        <p className="mb-4 text-sm text-slate-700">{t('emailUnavailable')}</p>
        <a href={fileUrl} download={fileName} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700">
          <Download className="h-3.5 w-3.5" aria-hidden />
          {t('download')}
        </a>
      </div>
    );
  }
  if (!email) {
    return (
      <div className="mt-16 text-center" role="status">
        <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-indigo-500" aria-hidden />
        <p className="text-xs text-slate-500">{t('loadingEmail')}</p>
      </div>
    );
  }

  const date = email.date_iso
    ? new Intl.DateTimeFormat(locale, {
      weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(email.date_iso))
    : email.date;
  const size = (bytes: number) =>
    new Intl.NumberFormat(locale, {
      style: 'unit',
      unit: bytes >= 1024 * 1024 ? 'megabyte' : 'kilobyte',
      maximumFractionDigits: bytes >= 1024 * 1024 ? 1 : 0,
    }).format(bytes >= 1024 * 1024 ? bytes / (1024 * 1024) : Math.max(1, bytes / 1024));
  const headers: Array<[string, string]> = [
    [t('from'), email.from],
    [t('to'), email.to],
    [t('cc'), email.cc],
    [t('date'), date],
  ];

  return (
    <article className="w-full max-w-3xl self-start rounded-lg bg-white shadow">
      <header className="border-b border-slate-200 px-5 py-4">
        <h2 className="text-lg font-semibold leading-snug text-slate-900">{email.subject || t('noSubject')}</h2>
        <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
          {headers.filter(([, value]) => value).map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-slate-500">{label}</dt>
              <dd className="min-w-0 break-words text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      {email.attachments.length > 0 && (
        <section className="border-b border-slate-200 px-5 py-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t('attachments', { count: email.attachments.length })}
          </h3>
          <ul className="flex flex-wrap gap-2">
            {email.attachments.map((attachment, index) => {
              const Icon = attachmentIcon(attachment);
              const label = (
                <>
                  <Icon className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                  <span className="max-w-[16rem] truncate">{attachment.filename}</span>
                  <span className="text-slate-400">{size(attachment.size)}</span>
                </>
              );
              const chip = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ring-1 ring-inset';
              return (
                <li key={`${attachment.filename}-${index}`}>
                  {attachment.in_case ? (
                    <button
                      type="button"
                      onClick={() => onOpenFile(attachment.filename)}
                      title={t('openAttachment', { file: attachment.filename })}
                      className={clsx(chip, 'bg-indigo-50 text-indigo-800 ring-indigo-200 hover:bg-indigo-100')}
                    >
                      {label}
                    </button>
                  ) : (
                    <span title={t('attachmentNotInCase')} className={clsx(chip, 'bg-slate-50 text-slate-600 ring-slate-200')}>
                      {label}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="px-5 py-4 text-sm leading-relaxed text-slate-800">
        {email.body_format === 'markdown'
          ? <MarkdownText>{email.body}</MarkdownText>
          : <div className="whitespace-pre-wrap break-words">{email.body}</div>}
      </div>
    </article>
  );
}
