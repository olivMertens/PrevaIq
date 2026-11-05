const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { load, srcDir } = require('./loadTs');

const libDir = path.join(srcDir, 'lib');
const documents = load('documentFiles.ts', libDir);
const caseUrl = load('caseUrl.ts', libDir);

// Pages of the Swiss storm case, as extracted (global page numbers across files).
const pages = [
  { file: 'schadenmeldung-geschaeftsversicherung.pdf', page_number: 1, language: 'de' },
  { file: 'schadenmeldung-geschaeftsversicherung.pdf', page_number: 2, language: 'de' },
  { file: 'schadenmeldung-geschaeftsversicherung.pdf', page_number: 3, language: 'de' },
  { file: 'email-01-schadenmeldung-de.eml', page_number: 4, language: 'de' },
  { file: 'email-02-loss-estimate-en.eml', page_number: 5, language: 'en' },
  { file: 'photos/IMG_20260828_104112.jpg', page_number: 6, language: null },
  { file: 'kostenvoranschlag.docx', page_number: 7, language: 'de' },
];

test('the document list shows one entry per file, with how the viewer displays it', () => {
  const grouped = documents.groupDocuments(pages);
  assert.deepEqual(
    grouped.map((doc) => [doc.name, doc.kind, doc.pages.map((page) => page.page_number), doc.language]),
    [
      ['schadenmeldung-geschaeftsversicherung.pdf', 'pdf', [1, 2, 3], 'de'],
      ['email-01-schadenmeldung-de.eml', 'email', [4], 'de'],
      ['email-02-loss-estimate-en.eml', 'email', [5], 'en'],
      ['IMG_20260828_104112.jpg', 'image', [6], null],
      ['kostenvoranschlag.docx', 'other', [7], 'de'],
    ],
  );
  assert.equal(documents.documentKind('Scan.PDF'), 'pdf');
  assert.equal(documents.documentKind('photo.HEIC'), 'other');
  assert.equal(documents.documentKind('mail.msg'), 'other');
});

test('a document is translated as a whole, starting with the page being read', () => {
  const claimForm = documents.groupDocuments(pages)[0].pages;
  const order = (selected, limit) => documents.translationOrder(claimForm, selected, limit).map((page) => page.page_number);
  assert.deepEqual(order(1), [1, 2, 3]);
  assert.deepEqual(order(2), [2, 3, 1]);
  assert.deepEqual(order(3), [3, 2, 1]);
  assert.deepEqual(order(2, 2), [2, 3]);
  // An unknown page starts from the first one.
  assert.deepEqual(order(99), [1, 2, 3]);

  const long = Array.from({ length: 40 }, (_, index) => ({ file: 'big.pdf', page_number: index + 1 }));
  const window = documents.translationOrder(long, 30, 24).map((page) => page.page_number);
  assert.equal(window.length, 24);
  assert.deepEqual(window.slice(0, 11), [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40]);
  assert.deepEqual(window.slice(11, 14), [29, 28, 27]);
});

test('the open case, tab and page live in the address bar and survive a reload', () => {
  const { withCaseParams, readCaseParams } = caseUrl;
  const opened = withCaseParams('', { app: 'fc8c3b98', persona: 'habitation_claims', conversation: null });
  assert.equal(opened, '?app=fc8c3b98&persona=habitation_claims');
  const reading = withCaseParams(opened, { view: 'source', page: 5 });
  assert.equal(reading, '?app=fc8c3b98&persona=habitation_claims&view=source&page=5');
  assert.deepEqual(readCaseParams(reading), {
    app: 'fc8c3b98', persona: 'habitation_claims', conversation: null, view: 'source', page: 5,
  });
  // Back to the overview: the tab and page leave the address bar; back to the dashboard: all of it.
  assert.equal(withCaseParams(reading, { view: null, page: null }), opened);
  assert.equal(withCaseParams(reading, { app: null, persona: null, view: null, page: null, conversation: null }), '');
  // Unknown tabs and invalid pages are ignored.
  assert.deepEqual(readCaseParams('?app=a&view=admin&page=-3'), {
    app: 'a', persona: null, conversation: null, view: null, page: null,
  });
  assert.equal(readCaseParams('?app=a&page=2.5').page, null);
});

test('the language switch reloads the page, which keeps the address bar', () => {
  const switcher = fs.readFileSync(path.join(srcDir, 'components', 'LanguageSwitcher.tsx'), 'utf8');
  const home = fs.readFileSync(path.join(srcDir, 'app', 'page.tsx'), 'utf8');
  const workbench = fs.readFileSync(path.join(srcDir, 'components', 'WorkbenchView.tsx'), 'utf8');
  assert.match(switcher, /window\.location\.reload\(\)/);
  assert.doesNotMatch(home, /replaceState\(\{\}, '', '\/'\)/, 'the open case must not be erased from the address bar');
  assert.match(home, /writeCaseParams\(\{ app: selectedAppId, persona: currentPersona/);
  assert.match(workbench, /writeCaseParams\(\{\s*view:/);
});

test('every document viewer label exists in English, French and German', () => {
  const keys = [
    'documents', 'photos', 'pageCount', 'pageOf', 'pageChip', 'email', 'originalLanguage', 'download',
    'noPreview', 'noPreviewHint', 'loadingEmail', 'emailUnavailable', 'noSubject', 'from', 'to', 'cc',
    'date', 'attachments', 'openAttachment', 'attachmentNotInCase', 'showInViewer',
  ];
  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'messages', `${locale}.json`), 'utf8'));
    const missing = keys.filter((key) => typeof messages.documentViewer?.[key] !== 'string');
    assert.deepEqual(missing, [], `${locale} documentViewer`);
    assert.equal(typeof messages.pageNavigator.summaries, 'string');
    assert.equal(typeof messages.pageNavigator.batchLabel, 'string');
  }
});
