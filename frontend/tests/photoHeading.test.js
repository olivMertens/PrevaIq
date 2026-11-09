const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {createTranslator} = require('use-intl/core');
const {load, srcDir} = require('./loadTs');
const documents = load('documentFiles.ts', path.join(srcDir, 'lib'));
const {swissGermanMessages} = load('locales.ts', path.join(srcDir, 'i18n'));

const filename = 'IMG_20260828_104355.jpg';
const source = `# Analyse des Photos: ${filename}\n\nDer Schaden ist auf dem Foto sichtbar. Die Uhr und die Werkzeuge sind nicht trocken.`;

function renderPane(locale, view = 'translated', file = filename) {
  const raw = JSON.parse(fs.readFileSync(
    path.join(srcDir, '..', 'messages', `${locale === 'de-CH' ? 'de' : locale}.json`), 'utf8',
  ));
  const messages = locale === 'de-CH' ? swissGermanMessages(raw) : raw;
  const module = {exports: {}};
  const filePath = path.join(srcDir, 'components', 'ExtractedTextPane.tsx');
  const {outputText} = ts.transpileModule(fs.readFileSync(filePath, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2020, esModuleInterop: true,
    },
  });
  vm.runInThisContext(`(function(module,exports,require){${outputText}\n})`, {filename: filePath})(
    module, module.exports, name => {
      if (name === 'next-intl') return {
        useTranslations: namespace => createTranslator({locale, messages, namespace}),
      };
      if (name === '@/lib/documentFiles') return documents;
      if (name === './ContentLanguageBar') return {__esModule: true, default: () => null};
      return require(name);
    },
  );
  const page = {page_number: 1, file, markdown: source, language: 'de'};
  const document = {name: file, file, kind: documents.documentKind(file), pages: [page]};
  const original = JSON.stringify(document);
  const html = renderToStaticMarkup(React.createElement(module.exports.default, {
    document, selectedPageNumber: 1, batchSummary: null, searchQuery: '',
    contentView: view, onContentViewChange() {}, pageTranslation: () => null, onSelectPage() {},
  }));
  assert.equal(JSON.stringify(document), original, 'The saved source must not be rewritten');
  return html;
}

for (const locale of ['de', 'de-CH']) {
  test(`${locale}: generated photo heading follows the UI even when its body is already German`, () => {
    const html = renderPane(locale);
    assert.ok(html.includes(`Fotoanalyse: ${filename}`));
    assert.ok(!html.includes(`Analyse des Photos: ${filename}`));
    assert.ok(html.includes('Die Uhr und die Werkzeuge sind nicht trocken.'));
  });
}

test('Original content mode preserves the exact stored photo heading and filename', () => {
  const html = renderPane('de-CH', 'original');
  assert.ok(html.includes(`Analyse des Photos: ${filename}`));
  assert.ok(html.includes('Originaltextansicht'));
  assert.ok(html.includes('Übersetzte Ansicht verwenden'));
});

test('known generated wrappers localize in every UI language without touching their body', () => {
  const titles = {en: 'Photo analysis', fr: 'Analyse photo', de: 'Fotoanalyse', 'de-CH': 'Fotoanalyse'};
  for (const [locale, title] of Object.entries(titles)) {
    for (const legacy of ['Analyse des Photos', 'Analyse photo', 'Photo analysis', 'Image analysis', 'Fotoanalyse', 'Bildanalyse']) {
      const input = `## ${legacy}: ${filename}\r\n\r\nOriginal body **unchanged**.`;
      const output = documents.localizeGeneratedPhotoHeading(
        input, `photos/${filename}`, name => `${title}: ${name}`,
      );
      assert.equal(output, `## ${title}: ${filename}\r\n\r\nOriginal body **unchanged**.`, locale);
    }
  }
});

test('real document headings, quotations, code and other filenames are not rewritten', () => {
  const title = name => `Fotoanalyse: ${name}`;
  for (const input of [
    `> # Analyse des Photos: ${filename}\nQuoted evidence`,
    `\`\`\`md\n# Analyse des Photos: ${filename}\n\`\`\``,
    `# Other heading\n# Analyse des Photos: ${filename}\nBody`,
    '# Analyse des Photos: another.jpg\nBody',
  ]) {
    assert.equal(documents.localizeGeneratedPhotoHeading(input, filename, title), input);
  }
  assert.equal(documents.localizeGeneratedPhotoHeading(source, 'source.pdf', title), source);
});

test('literal French UI labels are not hardcoded in JSX text or attributes', () => {
  const found = [];
  function scan(dir) {
    for (const item of fs.readdirSync(dir, {withFileTypes: true})) {
      const file = path.join(dir, item.name);
      if (item.isDirectory()) { scan(file); continue; }
      if (!file.endsWith('.tsx')) continue;
      const text = fs.readFileSync(file, 'utf8');
      const ast = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      function visit(node) {
        const value = ts.isJsxText(node) ? node.getText(ast).trim()
          : ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer)
            ? node.initializer.text : '';
        if (/[àâçéèêëîïôûùœ]|\b(?:Analyse des|Niveau d'urgence|Déclaration|Sinistre|Chargement|Aucun|Fermer|Précédent|Suivant)\b/i.test(value)) {
          found.push(`${path.relative(srcDir, file)}:${ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1}: ${value}`);
        }
        ts.forEachChild(node, visit);
      }
      visit(ast);
    }
  }
  scan(srcDir);
  assert.deepEqual(found, [], 'Static UI labels belong in the message catalogs, not JSX');
});
