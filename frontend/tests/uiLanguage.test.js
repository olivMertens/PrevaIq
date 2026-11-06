const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { load, srcDir } = require('./loadTs');
const localeHelpers = load('locales.ts', path.join(srcDir, 'i18n'));

const root = path.resolve(__dirname, '..');
const messages = (locale) => {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'messages', `${locale === 'de-CH' ? 'de' : locale}.json`), 'utf8'));
  return locale === 'de-CH' ? localeHelpers.swissGermanMessages(catalog) : catalog;
};
const source = (...parts) => fs.readFileSync(path.join(root, 'src', ...parts), 'utf8');
const PERSONA_IDS = ['underwriting', 'life_health_claims', 'automotive_claims', 'property_casualty_claims', 'habitation_claims', 'mortgage'];

test('persona descriptions follow the UI language', () => {
  const english = messages('en').persona.descriptions;
  const french = messages('fr').persona.descriptions;
  for (const locale of ['en', 'fr', 'de', 'de-CH']) {
    const descriptions = messages(locale).persona.descriptions;
    assert.deepEqual(PERSONA_IDS.filter((id) => typeof descriptions?.[id] !== 'string'), [], `${locale} persona.descriptions`);
  }
  assert.ok(PERSONA_IDS.every((id) => english[id] !== french[id]));
  assert.match(source('lib', 'PersonaContext.tsx'), /description: tDescription\(currentPersona\)/);
});

test('claims screens show the translated persona name, never the French registry name', () => {
  for (const [file, persona] of [
    ['AutomotiveClaimsOverview.tsx', 'automotive_claims'],
    ['LifeHealthClaimsOverview.tsx', 'life_health_claims'],
  ]) {
    const screen = source('components', 'claims', file);
    assert.match(screen, new RegExp(`boardLabel=\\{tPersona\\('${persona}'\\)\\}`), file);
    assert.doesNotMatch(screen.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ''), /Sinistres|Souscription/, file);
  }
});

test('the glossary menu is requested in the UI language and titled with the translated persona', () => {
  const dropdown = source('components', 'GlossaryDropdown.tsx');
  assert.match(dropdown, /getGlossary\(currentPersona, locale\)/);
  assert.match(dropdown, /t\('glossaryFor', \{ name: personaConfig\.name \}\)/);
  assert.doesNotMatch(dropdown, /searchGlossary/);
  for (const locale of ['en', 'fr', 'de', 'de-CH']) {
    assert.equal(typeof messages(locale).glossaryDropdown.originalLanguage, 'string', locale);
  }
});

test('rendered glossary headings ignore a French API name in English and German', async () => {
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const ts = require('typescript');
  const vm = require('node:vm');
  const { createTranslator } = await import('use-intl/core');
  const { outputText } = ts.transpileModule(source('components', 'GlossaryDropdown.tsx'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
    },
  });
  const expected = {
    en: 'Property Claims Glossary',
    fr: 'Glossaire Sinistres Habitation',
    de: 'Sachschäden Glossar',
    'de-CH': 'Sachschäden Glossar',
  };
  for (const locale of ['en', 'fr', 'de', 'de-CH']) {
    const catalog = messages(locale);
    let stateIndex = 0;
    const sourceModule = { exports: {} };
    const load = (specifier) => {
      if (specifier === 'react') return {
        ...React,
        useState: (initial) => {
          const index = stateIndex++;
          const value = index === 0 ? true : index === 4
            ? { count: 0, language: locale === 'de-CH' ? 'de' : locale, name: 'Sinistres Habitation' }
            : initial;
          return [value, () => {}];
        },
        useEffect: () => {},
        useRef: () => ({ current: null }),
        useMemo: (factory) => factory(),
        useCallback: (callback) => callback,
      };
      if (specifier === 'next-intl') return {
        useLocale: () => locale,
        useTranslations: (namespace) => createTranslator({ locale, messages: catalog, namespace }),
      };
      if (specifier === '@/i18n/locales') return localeHelpers;
      if (specifier === '@/lib/PersonaContext') return {
        usePersona: () => ({
          currentPersona: 'habitation_claims',
          personaConfig: { name: catalog.persona.labels.habitation_claims },
        }),
      };
      if (specifier === '@/lib/ToastProvider') return { useToast: () => ({ addToast: () => {} }) };
      if (specifier === '@/lib/api') return {
        getGlossary: () => { throw new Error('Rendering a heading must not call the API'); },
      };
      return require(specifier);
    };
    vm.runInThisContext(`(function(module, exports, require) {${outputText}\n})`)(
      sourceModule, sourceModule.exports, load
    );
    const html = renderToStaticMarkup(React.createElement(sourceModule.exports.default));
    assert.ok(html.includes(expected[locale]), `${locale}: expected ${expected[locale]}`);
    if (locale !== 'fr') assert.ok(!html.includes('Sinistres Habitation'));
    if (locale === 'de-CH') assert.ok(html.includes(catalog.glossaryDropdown.originalLanguage));
  }
});

test('English messages contain no French words outside quoted demo file names', () => {
  const french = /[àâçéèêëîïôûùüÿœ]|\b(sinistres?|souscription|hypothécaire|dossiers?|franchise|assurée?|garanties?)\b/i;
  const allowed = new Set(['customerAffiliation.addressPlaceholder']);
  const found = [];
  (function walk(node, key) {
    if (typeof node === 'string') {
      if (french.test(node) && !allowed.has(key)) found.push(`${key}: ${node}`);
    } else if (node && typeof node === 'object') {
      for (const [child, value] of Object.entries(node)) {
        if (!(key === '' && child === 'demoGuide')) walk(value, key ? `${key}.${child}` : child);
      }
    }
  })(messages('en'), '');
  assert.deepEqual(found, []);
});
