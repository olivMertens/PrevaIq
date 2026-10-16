'use client';

import {
  FileText,
  Image,
  ExternalLink,
  Download,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface GalleryItem {
  url: string;
  filename: string;
  type: 'pdf' | 'image' | 'video' | 'document';
  label?: string;
}

interface GalleryLightboxProps {
  items: GalleryItem[];
  currentIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

export default function GalleryLightbox({ items, currentIndex, onClose, onNavigate }: GalleryLightboxProps) {
  const t = useTranslations('gallery');
  if (items.length === 0) return null;

  const current = items[currentIndex];
  const isImage = current.type === 'image';
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < items.length - 1;

  return (
    <div className="fixed inset-0 z-[60] bg-black/85 flex flex-col" onClick={onClose}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/40 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 text-white text-sm min-w-0">
          <span className="px-2 py-0.5 rounded text-xs bg-white/20">{currentIndex + 1} / {items.length}</span>
          <span className="truncate">{current.filename}</span>
          {current.label && <span className="px-2 py-0.5 rounded text-xs bg-purple-500/60">{current.label}</span>}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <a href={current.url} download className="p-2 hover:bg-white/10 rounded-full transition-colors" title={t('download')}>
            <Download className="w-5 h-5 text-white" />
          </a>
          <a href={current.url} target="_blank" rel="noopener noreferrer" className="p-2 hover:bg-white/10 rounded-full transition-colors" title={t('openNewTab')}>
            <ExternalLink className="w-5 h-5 text-white" />
          </a>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full transition-colors" title={t('close')}>
            <X className="w-5 h-5 text-white" />
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 flex items-center justify-center relative min-h-0 p-4" onClick={(e) => e.stopPropagation()}>
        {hasPrev && (
          <button onClick={() => onNavigate(currentIndex - 1)}
            className="absolute left-4 top-1/2 -translate-y-1/2 p-3 bg-black/40 hover:bg-black/60 rounded-full transition-colors z-10"
            title={t('previous')}>
            <ChevronLeft className="w-6 h-6 text-white" />
          </button>
        )}

        {isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={current.url} alt={current.filename}
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl" />
        ) : (
          <iframe src={current.url} title={current.filename}
            className="w-full h-full max-w-5xl rounded-lg shadow-2xl bg-white" />
        )}

        {hasNext && (
          <button onClick={() => onNavigate(currentIndex + 1)}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-3 bg-black/40 hover:bg-black/60 rounded-full transition-colors z-10"
            title={t('next')}>
            <ChevronRight className="w-6 h-6 text-white" />
          </button>
        )}
      </div>

      {/* Bottom thumbnails strip */}
      <div className="flex items-center justify-center gap-2 px-4 py-3 bg-black/40 flex-shrink-0 overflow-x-auto" onClick={(e) => e.stopPropagation()}>
        {items.map((item, idx) => (
          <button key={idx} onClick={() => onNavigate(idx)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all whitespace-nowrap ${
              idx === currentIndex
                ? 'bg-white/20 text-white ring-2 ring-white/50'
                : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white'
            }`}>
            {item.type === 'image' ? <Image className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
            <span className="max-w-[120px] truncate">{item.filename}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
