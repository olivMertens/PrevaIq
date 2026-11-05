const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load(relativePath) {
  const filename = path.resolve(__dirname, '..', 'src', relativePath);
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const sourceModule = { exports: {} };
  vm.runInThisContext(`(function (module, exports) {${outputText}\n})`, { filename })(
    sourceModule,
    sourceModule.exports,
  );
  return sourceModule.exports;
}

const { previewUrl } = load('lib/media.ts');

test('case photos are requested as compressed previews', () => {
  assert.equal(
    previewUrl('/api/applications/e98d6523/files/cave-inondee.png', 'thumb'),
    '/api/applications/e98d6523/files/cave-inondee.png?preview=thumb',
  );
  assert.equal(
    previewUrl('/api/applications/APP/files/2026-04-14%20145147-mai-image-2.PNG', 'screen'),
    '/api/applications/APP/files/2026-04-14%20145147-mai-image-2.PNG?preview=screen',
  );
  assert.equal(
    previewUrl('/api/applications/APP/files/photo%201.jpg?v=2', 'thumb'),
    '/api/applications/APP/files/photo%201.jpg?v=2&preview=thumb',
  );
  assert.equal(
    previewUrl('/api/applications/APP/files/photo.jpg?preview=thumb', 'screen'),
    '/api/applications/APP/files/photo.jpg?preview=screen',
  );
});

test('documents, external images and malformed names keep their original URL', () => {
  for (const url of [
    '/api/applications/APP/files/declaration.pdf#page=2',
    '/api/policy-pdfs/habitation',
    'https://example.test/photo.png',
    '/prevaiq-logo.png',
    '',
  ]) {
    assert.equal(previewUrl(url, 'thumb'), url);
  }
  assert.equal(
    previewUrl('/api/applications/APP/files/bad%E0name.png', 'thumb'),
    '/api/applications/APP/files/bad%E0name.png?preview=thumb',
  );
});
