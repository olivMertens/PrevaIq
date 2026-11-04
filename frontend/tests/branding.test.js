const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { existsSync, readFileSync } = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const ts = require('typescript');

const frontend = path.resolve(__dirname, '..');
const root = path.resolve(frontend, '..');

// Approved FDR SHA-256 values, pinned here so CI never needs a sibling checkout.
const assets = [
  {
    hash: '07f71da8bf7bab8a42eada5172aefc91c97c19e9c18561a0443c1cb6b912537d',
    paths: ['frontend/public/favicon.svg', 'frontend/public/favicon-prevaiq.svg', 'assets/logos/icon-prevaiq.svg'],
  },
  {
    hash: '6c4719949007b8c703018e000f9b1f59fce8554b2882b614854dc9f554fcaead',
    paths: ['assets/logos/prevaiq_icon.png', 'frontend/public/prevaiq-icon.png'],
  },
  {
    hash: '4fa52fcdefc3ec31e8dc3f4c8cff1da2b179cd18b5dae66d3058d02c4c28f27e',
    paths: ['assets/logos/prevaiq_icon_dark.png', 'frontend/public/prevaiq-icon-dark.png'],
  },
  {
    hash: 'c9b5a2a2465aa0b5f6ab5da806774538925259f7a193d2779a22356892cb306b',
    paths: [
      'assets/logos/prevaiq_logo.png', 'frontend/public/prevaiq-logo.png',
      'assets/logo-prevaiq.png', 'assets/logos/logo-prevaiq.png',
    ],
  },
  {
    hash: 'befd7f636abde702e627d393a8c24f01eba55e210aa8ade2dfe265e195a0cea8',
    paths: ['assets/logos/prevaiq_logo_dark.png', 'frontend/public/prevaiq-logo-dark.png'],
  },
  {
    hash: '2aa88cda81d71d6517830b7f787770f1ea6d181f95872e1c661c37ebc731dd6c',
    paths: ['assets/logos/prevaiq-logo.svg', 'frontend/public/prevaiq-logo.svg'],
  },
];

for (const asset of assets) {
  for (const filename of asset.paths) {
    test(`${filename} is byte-identical to the approved FDR asset`, () => {
      const bytes = readFileSync(path.join(root, filename));
      assert.equal(createHash('sha256').update(bytes).digest('hex'), asset.hash);
    });
  }
}

test('byte-pinned SVGs are protected from Git line-ending conversion on every OS', () => {
  const attributes = readFileSync(path.join(root, '.gitattributes'), 'utf8');
  for (const asset of assets) {
    for (const filename of asset.paths.filter(name => name.endsWith('.svg'))) {
      assert.ok(attributes.split(/\r?\n/).includes(`${filename} binary`), filename);
    }
  }
});

// Same lightweight TS/VM approach as auth.test.js; no test-only dependencies.
function loadSource(relative, overrides = {}) {
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const sourceModule = { exports: {} };
    cache.set(filename, sourceModule.exports);
    const nativeRequire = createRequire(filename);
    const requireSource = (name) => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (name.startsWith('@/')) {
        const target = path.join(frontend, 'src', name.slice(2));
        return load(existsSync(`${target}.ts`) ? `${target}.ts` : `${target}.tsx`);
      }
      if (name.endsWith('.css')) return {};
      return nativeRequire(name);
    };
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
      },
    });
    vm.runInNewContext(outputText, {
      module: sourceModule, exports: sourceModule.exports, require: requireSource,
      process: { env: {} },
    }, { filename });
    return sourceModule.exports;
  }
  return load(path.join(frontend, 'src', relative));
}

test('brand paths resolve to official public files, including both surface variants', () => {
  const { brand } = loadSource('lib/brand.ts');
  for (const key of ['logo', 'logoDark', 'icon', 'iconDark', 'favicon']) {
    assert.ok(existsSync(path.join(frontend, 'public', brand[key])), key);
  }
  assert.equal(brand.logo, '/prevaiq-logo.png');
  assert.equal(brand.logoDark, '/prevaiq-logo-dark.png');
  assert.equal(brand.icon, '/prevaiq-icon.png');
  assert.equal(brand.iconDark, '/prevaiq-icon-dark.png');
  assert.equal(brand.favicon, '/favicon.svg');
});

for (const surface of ['light', 'dark']) {
  for (const compact of [false, true]) {
    test(`BrandMark renders the accessible official ${surface} wordmark (compact=${compact})`, () => {
      const BrandMark = loadSource('components/BrandMark.tsx').default;
      const markup = renderToStaticMarkup(React.createElement(BrandMark, { surface, compact }));
      const expected = surface === 'dark' ? '/prevaiq-logo-dark.png' : '/prevaiq-logo.png';
      assert.ok(markup.includes(`src="${expected}"`), markup);
      assert.match(markup, /alt="PrevaIQ"/);
      assert.match(markup, /width="859"/);
      assert.match(markup, /height="254"/);
      assert.ok(markup.includes(compact ? 'h-9' : 'h-11'));
      assert.match(markup, /w-auto.*object-contain/);
      assert.doesNotMatch(markup, /<svg|brightness-|invert|filter:|_next\/image/);
      assert.equal((markup.match(/<img /g) || []).length, 1);
    });
  }
}

test('root metadata uses the exact SVG favicon and a PNG touch icon', () => {
  const { metadata } = loadSource('app/layout.tsx', {
    'next/font/google': { Inter: () => ({ className: 'test-font' }) },
    '@/lib/PersonaContext': {}, '@/lib/ToastProvider': {},
    'next-intl': {}, 'next-intl/server': {},
  });
  assert.equal(metadata.title, 'PrevaIQ');
  assert.equal(metadata.icons.icon.url, '/favicon.svg');
  assert.equal(metadata.icons.icon.type, 'image/svg+xml');
  assert.equal(metadata.icons.icon.sizes, 'any');
  assert.equal(metadata.icons.shortcut, '/favicon.svg');
  assert.equal(metadata.icons.apple.url, '/prevaiq-icon.png');
  assert.equal(metadata.icons.apple.type, 'image/png');
  assert.equal(metadata.icons.apple.sizes, '240x240');
});

test('all UI brand surfaces share BrandMark rather than reconstructed logos', () => {
  for (const filename of [
    'components/TopNav.tsx', 'components/Sidebar.tsx', 'components/auth/LoginHero.tsx',
    'components/DemoGuideModal.tsx', 'app/access/page.tsx', 'app/admin/page.tsx',
    'app/customers/page.tsx', 'app/customers/[id]/page.tsx',
  ]) {
    const source = readFileSync(path.join(frontend, 'src', filename), 'utf8');
    assert.match(source, /<BrandMark[\s/>]/, filename);
    assert.doesNotMatch(source, /src=\{brand\.logo\}|giq-grad|brandmark-grad|brightness-0 invert/, filename);
  }
  const sidebar = readFileSync(path.join(frontend, 'src/components/Sidebar.tsx'), 'utf8');
  assert.match(sidebar, /<BrandMark compact surface="dark"\s*\/>/);
});
