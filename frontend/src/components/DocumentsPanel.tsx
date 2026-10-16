'use client';

import { useState, useMemo } from 'react';
import { FileText, Download, ExternalLink, Image, Film, ZoomIn } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getMediaUrl } from '@/lib/api';
import type { StoredFile } from '@/lib/types';
import GalleryLightbox from './GalleryLightbox';
import type { GalleryItem } from './GalleryLightbox';

interface DocumentsPanelProps {
  files: StoredFile[];
  applicationId?: string;
}

function getFileType(filename: string): { label: string; icon: 'pdf' | 'image' | 'video' | 'document' } {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'heic'];
  const videoExts = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'm4v'];
  if (ext === 'pdf') return { label: 'PDF', icon: 'pdf' };
  if (imageExts.includes(ext)) return { label: ext.toUpperCase(), icon: 'image' };
  if (videoExts.includes(ext)) return { label: ext.toUpperCase(), icon: 'video' };
  return { label: ext.toUpperCase() || 'File', icon: 'document' };
}

function FileIcon({ type }: { type: string }) {
  switch (type) {
    case 'image': return <Image className="w-6 h-6 text-emerald-600" />;
    case 'video': return <Film className="w-6 h-6 text-purple-600" />;
    default: return <FileText className="w-6 h-6 text-indigo-600" />;
  }
}

function getProxyUrl(file: StoredFile, applicationId?: string): string {
  // Always use the API proxy URL which handles auth
  if (applicationId) {
    return getMediaUrl(`/api/applications/${applicationId}/files/${encodeURIComponent(file.filename)}`);
  }
  // Fallback to file.url if available, routed through proxy
  if (file.url) {
    // If it's a direct blob URL, rewrite to API proxy
    if (file.url.includes('blob.core.windows.net')) {
      return getMediaUrl(`/api/applications/${file.path.split('/')[1] || ''}/files/${encodeURIComponent(file.filename)}`);
    }
    return getMediaUrl(file.url);
  }
  return '';
}

export default function DocumentsPanel({ files, applicationId }: DocumentsPanelProps) {
  const t = useTranslations('documents');
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const galleryItems: GalleryItem[] = useMemo(() => {
    if (!applicationId) return [];
    return files.map(file => {
      const fileType = getFileType(file.filename);
      return {
        url: getProxyUrl(file, applicationId),
        filename: file.filename,
        type: fileType.icon as GalleryItem['type'],
        label: fileType.label,
      };
    });
  }, [files, applicationId]);

  if (!files || files.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('title')}</h2>
        <div className="text-center py-8 text-gray-500">
          <FileText className="w-12 h-12 mx-auto mb-2 text-gray-400" />
          <p>{t('noDocuments')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">
          {t('title')} ({files.length})
        </h2>
      </div>

      <div className="space-y-4">
        {files.map((file, index) => {
          const fileType = getFileType(file.filename);
          const proxyUrl = getProxyUrl(file, applicationId);
          return (
            <div
              key={index}
              className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer"
              onClick={() => setLightboxIndex(index)}
            >
              <div className="flex items-center gap-4">
                <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                  fileType.icon === 'image' ? 'bg-emerald-100' :
                  fileType.icon === 'video' ? 'bg-purple-100' : 'bg-indigo-100'
                }`}>
                  <FileIcon type={fileType.icon} />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900">{file.filename}</h3>
                  <p className="text-sm text-gray-500">
                    {fileType.label} • {t('uploaded')}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {proxyUrl && (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); setLightboxIndex(index); }}
                      className="p-2 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-50 rounded-lg transition-colors"
                      title={t('view')}
                    >
                      <ZoomIn className="w-5 h-5" />
                    </button>
                    <a
                      href={proxyUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                      title={t('openNewTab')}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-5 h-5" />
                    </a>
                    <a
                      href={proxyUrl}
                      download={file.filename}
                      className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                      title={t('download')}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Download className="w-5 h-5" />
                    </a>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 p-4 bg-indigo-50 rounded-lg">
        <p className="text-sm text-indigo-700">
          <strong>{t('tip')}:</strong> {t('tipText')}
        </p>
      </div>

      {/* Gallery Lightbox */}
      {lightboxIndex !== null && galleryItems.length > 0 && (
        <GalleryLightbox
          items={galleryItems}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </div>
  );
}
