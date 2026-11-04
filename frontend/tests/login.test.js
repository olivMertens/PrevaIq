const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const ts = require('typescript');

const frontend = path.resolve(__dirname, '..');
const messages = Object.fromEntries(['en', 'fr', 'de'].map(locale => [locale, require(`../messages/${locale}.json`).auth]));
const css = new Proxy({}, { get: (_, name) => name });

// Same TS/VM strategy as the existing branding/auth suites; no added dependency.
function loadUI({ locale = 'en', providers = {}, react = React, globals = {}, overrides = {} } = {}) {
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const sourceModule = { exports: {} };
    cache.set(filename, sourceModule.exports);
    const nativeRequire = createRequire(filename);
    const requireSource = name => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (name === 'react') return react;
      if (name === 'next-intl') return { useLocale: () => locale, useTranslations: () => key => {
        assert.equal(typeof messages[locale][key], 'string', `${locale}: ${key}`);
        return messages[locale][key];
      } };
      if (name === '@/components/auth/useAuthProviders') return {
        useAuthProviders: () => ({ loaded: true, entraEnabled: false, localAuthEnabled: false, requestEmail: 'demo@example.test', ...providers }),
        mailtoHref: (email, subject, body) => `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`,
      };
      if (name.endsWith('.css')) return { __esModule: true, default: css };
      if (name.startsWith('@/') || name.startsWith('.')) {
        const target = name.startsWith('@/') ? path.join(frontend, 'src', name.slice(2)) : path.resolve(path.dirname(filename), name);
        return load(existsSync(`${target}.ts`) ? `${target}.ts` : `${target}.tsx`);
      }
      return nativeRequire(name);
    };
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    });
    vm.runInNewContext(outputText, {
      module: sourceModule, exports: sourceModule.exports, require: requireSource, process: { env: {} },
      URLSearchParams, ...globals,
    }, { filename });
    return sourceModule.exports;
  }
  return name => load(path.join(frontend, 'src', name));
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return undefined;
  if (predicate(node)) return node;
  for (const child of React.Children.toArray(node.props?.children)) {
    const found = find(child, predicate);
    if (found) return found;
  }
}
function hooks(initial = []) {
  const state = [];
  const effects = [];
  let index = 0;
  return {
    state, effects,
    react: { ...React, useContext: () => 'light', useTransition: () => [false, fn => fn()],
      useEffect: fn => effects.push(fn),
      useState: fallback => {
        const i = index++;
        state[i] = i < initial.length ? initial[i] : fallback;
        return [state[i], value => { state[i] = typeof value === 'function' ? value(state[i]) : value; }];
      },
    },
  };
}

for (const locale of ['en', 'fr', 'de']) {
  for (const theme of ['light', 'dark']) {
    for (const [entraEnabled, localAuthEnabled] of [[true, false], [true, true], [false, true], [false, false]]) {
      test(`login ${locale}/${theme}, Entra=${entraEnabled}, local=${localAuthEnabled}: composition, branding, links and provider gates`, () => {
        const load = loadUI({ locale, providers: { entraEnabled, localAuthEnabled } });
        const Shell = load('components/auth/LoginShell.tsx').default;
        const Page = load('app/login/page.tsx').default;
        const markup = renderToStaticMarkup(React.createElement(Shell, { initialTheme: theme }, React.createElement(Page)));
        assert.match(markup, new RegExp(`<main class="login" data-theme="${theme}">`));
        assert.equal((markup.match(/<main /g) || []).length, 1);
        assert.ok(markup.indexOf('class="top"') < markup.indexOf('class="layout"'));
        assert.ok(markup.indexOf('class="hero"') < markup.indexOf('class="card"'));
        assert.match(markup, /role="group"/);
        assert.match(markup, /aria-pressed="true"/);
        assert.match(markup, /aria-pressed="false"/);
        assert.match(markup, /src="\/prevaiq-logo-dark.png"/);
        assert.match(markup, new RegExp(`class="cardBrand"><img[^>]*src="/prevaiq-logo${theme === 'dark' ? '-dark' : ''}.png"`));
        assert.equal(markup.includes('href="/api/auth/entra/login"'), entraEnabled);
        assert.equal(markup.includes('<form'), localAuthEnabled);
        assert.equal(/autocomplete="username"/i.test(markup), localAuthEnabled);
        assert.equal(/autocomplete="current-password"/i.test(markup), localAuthEnabled);
        assert.equal(markup.includes('role="alert"'), !entraEnabled && !localAuthEnabled);
        assert.ok(markup.includes('href="mailto:demo@example.test?subject='));
        assert.ok(markup.includes('href="mailto:demo@example.test"'));
        for (const key of ['splashTitle', 'splashLead', 'splashPoint1', 'splashPoint2', 'splashPoint3', 'splashFraudNotice']) {
          assert.ok(markup.includes(messages[locale][key].replaceAll('&', '&amp;').replaceAll("'", '&#x27;')), key);
        }
      });
    }
  }
}

test('missing request contact does not create access-request or contact links', () => {
  const load = loadUI({ providers: { entraEnabled: true, requestEmail: null } });
  const Page = load('app/login/page.tsx').default;
  const markup = renderToStaticMarkup(React.createElement(Page));
  assert.doesNotMatch(markup, /href="mailto:/);
  assert.match(markup, /href="\/api\/auth\/entra\/login"/);
});

test('login server layout restores only valid login-theme cookie values', async () => {
  for (const value of ['light', 'dark', 'invalid', undefined]) {
    const load = loadUI({ overrides: { 'next/headers': { cookies: async () => ({ get: name => {
      assert.equal(name, 'login-theme'); return value ? { value } : undefined;
    } }) } } });
    const element = await load('app/login/layout.tsx').default({ children: 'test' });
    assert.equal(element.props.initialTheme, value === 'dark' ? 'dark' : 'light');
  }
});

for (const theme of ['light', 'dark']) {
  test(`theme toggle ${theme} persists a login-only cookie without touching the application document`, () => {
    const h = hooks(); const document = {};
    const load = loadUI({ react: h.react, globals: { document } });
    const tree = load('components/auth/LoginShell.tsx').default({ initialTheme: theme, children: null });
    const button = find(tree, node => node.type === 'button');
    button.props.onClick();
    const next = theme === 'dark' ? 'light' : 'dark';
    assert.equal(h.state[0], next);
    assert.equal(document.cookie, `login-theme=${next};path=/login;max-age=31536000;samesite=lax`);
    assert.equal(Object.keys(document).join(','), 'cookie');
  });
}

for (const locale of ['en', 'fr']) {
  test(`language segments ${locale} preserve the locale cookie and reload behavior`, () => {
    const h = hooks(); const document = {}; let reloads = 0;
    const load = loadUI({ locale, react: h.react, globals: { document, window: { location: { reload: () => reloads++ } } } });
    const tree = load('components/LanguageSwitcher.tsx').default({ variant: 'login' });
    const selected = find(tree, node => node.type === 'button' && node.props['aria-pressed']);
    selected.props.onClick(); assert.equal(reloads, 0);
    const other = find(tree, node => node.type === 'button' && !node.props['aria-pressed']);
    other.props.onClick(); assert.equal(reloads, 1);
    assert.equal(document.cookie, `locale=${locale === 'en' ? 'fr' : 'en'};path=/;max-age=31536000;samesite=lax`);
  });
}

for (const [status, flag] of [[200, 'success'], [409, 'alreadyConnected'], [429, 'capacityFull'], [401, 'error'], [500, 'fallback'], ['network', 'fallback']]) {
  test(`local login status ${status} preserves request payload, feedback and redirect`, async () => {
    const h = hooks([' demo ', 'test-password']); const window = { location: { href: '', search: '' } }; let payload;
    const load = loadUI({ react: h.react, providers: { localAuthEnabled: true }, globals: { window, fetch: async (url, options) => {
      assert.equal(url, '/api/auth/login'); assert.equal(options.method, 'POST');
      assert.equal(options.headers['Content-Type'], 'application/json'); payload = JSON.parse(options.body);
      if (status === 'network') throw new Error('test network failure');
      return { ok: status === 200, status, json: async () => status === 401 ? { error: 'test-denied' } : {} };
    } } });
    const tree = load('app/login/page.tsx').default(); let prevented = false;
    await find(tree, node => node.type === 'form').props.onSubmit({ preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true);
    assert.deepEqual(payload, { username: 'demo', password: 'test-password' });
    assert.equal(window.location.href, flag === 'success' ? '/' : '');
    assert.equal(h.state[3], flag === 'capacityFull');
    assert.equal(h.state[4], flag === 'alreadyConnected');
    assert.equal(h.state[2], flag === 'error' ? 'test-denied' : flag === 'fallback' ? messages.en.error : '');
    assert.equal(h.state[5], false);
  });
}

test('callback errors retain localized state/Entra/capacity feedback', () => {
  for (const locale of ['en', 'fr']) for (const [code, key] of Object.entries({ state: 'errorState', entra: 'errorEntra', capacity: 'errorCapacity' })) {
    const h = hooks();
    const load = loadUI({ locale, react: h.react, globals: { window: { location: { search: `?error=${code}&returnUrl=%2Fadmin` } } } });
    load('app/login/page.tsx').default(); h.effects.forEach(fn => fn());
    assert.equal(h.state[2], messages[locale][key]);
  }
});

test('EN/FR/DE locales are exposed and all new auth strings exist in each', () => {
  for (const key of ['splashEyebrow', 'languageLabel', 'languageEnglish', 'languageFrench', 'useLightTheme', 'useDarkTheme']) {
    for (const locale of ['en', 'fr', 'de']) assert.equal(typeof messages[locale][key], 'string');
  }
  const switcher = readFileSync(path.join(frontend, 'src/components/LanguageSwitcher.tsx'), 'utf8');
  assert.deepEqual([...switcher.matchAll(/code: '([^']+)'/g)].map(match => match[1]), ['en', 'fr', 'de']);
});

test('Nemo dimensions, control grouping, mobile breakpoints, theme and focus are scoped to login', () => {
  const source = readFileSync(path.join(frontend, 'src/components/auth/login.module.css'), 'utf8');
  assert.match(source, /width: min\(1060px, 100%\)/);
  assert.match(source, /grid-template-columns: minmax\(0, 1\.05fr\) minmax\(360px, 0\.95fr\)/);
  assert.match(source, /min-height: 560px/);
  assert.match(source, /\.top\s*\{[^}]*top: 16px;[^}]*right: 20px;[^}]*gap: 8px/s);
  assert.match(source, /\.login\[data-theme="dark"\]/);
  assert.match(source, /max-width: 800px/); assert.match(source, /max-width: 440px/);
  assert.match(source, /:focus-visible/); assert.match(source, /prefers-reduced-motion/);
  assert.match(source, /\.card a\[href="\/api\/auth\/entra\/login"\]\s*\{\s*box-shadow: none;\s*\}/);
  assert.match(source, /\.login \.languageOption:focus-visible\s*\{\s*outline-offset: 1px;\s*\}/);
  assert.match(source, /\.login\[data-theme="dark"\]\s*\{[^}]*--pq-accent-2: #22d3ee;/s);
  assert.doesNotMatch(source, /:root|\bbody\s*\{|\bhtml\s*\{/);
});


for (const theme of ['light', 'dark']) {
  test(`login ${theme} palette keeps navy actions, teal focus/links and exact Nemo background tokens local`, () => {
    const source = readFileSync(path.join(frontend, 'src/components/auth/login.module.css'), 'utf8');
    const selector = theme === 'dark' ? /\.login\[data-theme="dark"\]\s*\{([^}]+)\}/ : /\.login\s*\{([^}]+)\}/;
    const block = source.match(selector)[1];
    const tokens = Object.fromEntries([...block.matchAll(/(--pq-[\w-]+):\s*([^;]+);/g)].map(match => [match[1], match[2]]));
    const expected = theme === 'dark' ? {
      '--pq-action': '#2e5486', '--pq-accent': '#6fd0c4', '--pq-accent-2': '#22d3ee', '--pq-link': 'var(--pq-accent)',
      '--pq-bg': '#0f2036', '--pq-surface': '#13273f', '--pq-surface-2': '#16263c', '--pq-border': '#24384f', '--pq-footer-bg': '#14243a',
    } : {
      '--pq-action': '#203859', '--pq-accent': '#61c1b6', '--pq-accent-2': '#16bdca', '--pq-link': 'var(--pq-action)',
      '--pq-bg': '#f5f7fa', '--pq-surface': '#ffffff', '--pq-surface-2': '#eef2f7', '--pq-border': '#e3e8ef', '--pq-footer-bg': '#1c2f47',
    };
    for (const [name, value] of Object.entries(expected)) assert.equal(tokens[name], value, `${theme}: ${name}`);
    assert.doesNotMatch(source, /#(?:1d4ed8|2563eb|2f6fed|7aa7ff)/i);
    assert.match(source, /\.languageOption\[aria-pressed="true"\]\s*\{[^}]*background: var\(--pq-action\)/);
    assert.match(source, /\.card \.secondary\s*\{[^}]*color: var\(--pq-link\)/);
    assert.match(source, /:focus-visible\s*\{[^}]*outline: 2px solid var\(--pq-accent\)/);
  });
}
