'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { X, Loader2 } from 'lucide-react';
import { getMediaUrl } from '@/lib/api';
import { useTranslations } from 'next-intl';

interface FloatingPdfPreviewProps {
  applicationId: string;
  fileName: string;
  pageNumber: number;
  /** Anchor rect from the badge that triggered the preview */
  anchorRect: DOMRect;
  onClose: () => void;
}

/**
 * A floating PDF preview panel that appears when hovering over page
 * reference badges in the deep dive view.  Renders an iframe pointing
 * at the same PDF endpoint used by InlinePdfViewer.
 */
export default function FloatingPdfPreview({
  applicationId,
  fileName,
  pageNumber,
  anchorRect,
  onClose,
}: FloatingPdfPreviewProps) {
  const t = useTranslations('pdfViewer');
  const panelRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);

  const pdfBaseUrl = useMemo(
    () => getMediaUrl(`/api/applications/${applicationId}/files/${fileName}`),
    [applicationId, fileName]
  );
  const pdfUrl = `${pdfBaseUrl}#page=${pageNumber}&toolbar=0&navpanes=0&view=FitH`;

  // Compute position: prefer showing to the left of the badge.
  // If not enough room, show to the right.
  const PANEL_W = 480;
  const PANEL_H = 520;
  const GAP = 8;

  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  useEffect(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left: number;
    let top: number;

    // Try placing to the right of the badge first
    if (anchorRect.right + GAP + PANEL_W < vw) {
      left = anchorRect.right + GAP;
    } else if (anchorRect.left - GAP - PANEL_W > 0) {
      // Fall back to left side
      left = anchorRect.left - GAP - PANEL_W;
    } else {
      // Centre horizontally as last resort
      left = Math.max(8, (vw - PANEL_W) / 2);
    }

    // Vertically: align to the middle of the badge, clamped to viewport
    top = anchorRect.top + anchorRect.height / 2 - PANEL_H / 2;
    top = Math.max(8, Math.min(top, vh - PANEL_H - 8));

    setPosition({ top, left });
  }, [anchorRect]);

  // Close if user clicks outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Small delay so the click that opened it doesn't immediately close it
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 100);
    return () => {
      clearTimeout(id);
      document.removeEventListener('mousedown', handler);
    };
  }, [onClose]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      ref={panelRef}
      className="fixed z-[100] rounded-xl shadow-2xl border border-slate-200 bg-white overflow-hidden flex flex-col"
      style={{
        width: PANEL_W,
        height: PANEL_H,
        top: position.top,
        left: position.left,
      }}
      onMouseLeave={onClose}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200 flex-shrink-0">
        <span className="text-xs font-medium text-slate-700">
          Page {pageNumber} — {fileName.split('/').pop()}
        </span>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* PDF iframe */}
      <div className="flex-1 relative bg-slate-100">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t('loadingPage', { pageNumber })}
            </div>
          </div>
        )}
        <iframe
          src={pdfUrl}
          className="w-full h-full border-0"
          onLoad={() => setLoading(false)}
          title={t('pdfPreviewPage', { pageNumber })}
        />
      </div>
    </div>
  );
}
