// Files of a case as the document viewer lists them: one document per file with its pages.
// Pure module (no imports) so tests can load it without the Next.js toolchain.

export type DocumentKind = 'pdf' | 'image' | 'email' | 'other';

export interface DocumentPage {
  file: string;
  page_number: number;
  language?: string | null;
}

export interface CaseDocument<P extends DocumentPage = DocumentPage> {
  file: string;
  /** File name without its folder. */
  name: string;
  kind: DocumentKind;
  pages: P[];
  /** Most frequent detected language of the pages, null when unknown. */
  language: string | null;
}

const IMAGE_FILE = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i;

/** How the viewer shows a file: PDF, image, e-mail (.eml) or no preview. */
export function documentKind(file: string): DocumentKind {
  const name = file.toLowerCase();
  if (name.endsWith('.pdf')) return 'pdf';
  if (IMAGE_FILE.test(name)) return 'image';
  if (name.endsWith('.eml')) return 'email';
  return 'other';
}

export function documentName(file: string): string {
  return file.split(/[\\/]/).pop() || file;
}

function mainLanguage(pages: DocumentPage[]): string | null {
  const counts = new Map<string, number>();
  for (const page of pages) {
    if (page.language) counts.set(page.language, (counts.get(page.language) ?? 0) + 1);
  }
  let best: string | null = null;
  for (const [language, count] of counts) {
    if (best === null || count > (counts.get(best) ?? 0)) best = language;
  }
  return best;
}

/** Pages grouped by file, in the order the files first appear. */
export function groupDocuments<P extends DocumentPage>(pages: P[]): CaseDocument<P>[] {
  const byFile = new Map<string, P[]>();
  for (const page of pages) {
    const file = page.file || 'document';
    byFile.set(file, [...(byFile.get(file) ?? []), page]);
  }
  return Array.from(byFile, ([file, filePages]) => ({
    file,
    name: documentName(file),
    kind: documentKind(file),
    pages: filePages,
    language: mainLanguage(filePages),
  }));
}

/**
 * Pages of a document in translation order: the page being read first, then the following
 * pages, then the previous ones. Long documents are limited to the pages around the reader.
 */
export function translationOrder<P extends DocumentPage>(pages: P[], selectedPage: number, limit = 24): P[] {
  const index = Math.max(0, pages.findIndex((page) => page.page_number === selectedPage));
  return [...pages.slice(index), ...pages.slice(0, index).reverse()].slice(0, limit);
}
