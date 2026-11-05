// Compressed previews of case images served by the API (`?preview=thumb|screen`).
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type PreviewSize = 'thumb' | 'screen';

const CASE_FILE_PATH = /\/api\/applications\/[^/?#]+\/files\/[^?#]+$/;
const PREVIEWABLE_EXTENSION = /\.(png|jpe?g|gif|bmp|tiff?|webp)$/i;

function fileName(path: string): string {
  const raw = path.slice(path.lastIndexOf('/') + 1);
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/**
 * URL of a resized, compressed version of a case image (thumbnails: 480 px, screen: 1600 px).
 * Other files and external URLs are returned unchanged; downloads keep the original URL.
 */
export function previewUrl(url: string, size: PreviewSize): string {
  if (!url) return url;
  const hashIndex = url.indexOf('#');
  const hash = hashIndex >= 0 ? url.slice(hashIndex) : '';
  const withoutHash = hashIndex >= 0 ? url.slice(0, hashIndex) : url;
  const queryIndex = withoutHash.indexOf('?');
  const path = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash;
  if (!CASE_FILE_PATH.test(path) || !PREVIEWABLE_EXTENSION.test(fileName(path))) return url;

  const params = new URLSearchParams(queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : '');
  params.set('preview', size);
  return `${path}?${params.toString()}${hash}`;
}
