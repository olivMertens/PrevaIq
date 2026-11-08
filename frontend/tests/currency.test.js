const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const React = require('react');
const ts = require('typescript');
const { load, srcDir } = require('./loadTs');
const currency = load('currency.ts', path.join(srcDir, 'lib'));
const mortgage = load('format.ts', path.join(srcDir, 'components', 'mortgage'));

test('only USD, EUR and CHF are supported and the persisted reference defaults to EUR', () => {
  assert.deepEqual(currency.CURRENCIES, ['USD', 'EUR', 'CHF']);
  for (const code of currency.CURRENCIES) assert.equal(currency.resolveReferenceCurrency(code), code);
  for (const invalid of [undefined, '', 'usd', 'invalid']) {
    assert.equal(currency.isCurrencyCode(invalid), false);
    assert.equal(currency.resolveReferenceCurrency(invalid), 'EUR');
  }
});

test('explicit dossier currencies take precedence over every reference choice without mutating data', () => {
  for (const reference of currency.CURRENCIES) {
    for (const explicit of currency.CURRENCIES) {
      const application = Object.freeze({ jurisdiction: Object.freeze({ currency: explicit }) });
      assert.equal(currency.applicationCurrency(application, reference), explicit);
    }
    for (const app of [null, undefined, {}, { jurisdiction: {} }]) {
      assert.equal(currency.applicationCurrency(app, reference), reference);
    }
  }
});

test('currency formatting preserves values and existing Swiss grouping for each UI language', () => {
  for (const locale of ['en', 'fr', 'de', 'de-CH']) {
    for (const code of currency.CURRENCIES) {
      const formatLocale = code === 'CHF' ? `${locale.split('-')[0]}-CH` : locale;
      const expected = new Intl.NumberFormat(formatLocale, {
        style: 'currency', currency: code, maximumFractionDigits: 0,
      }).format(1697400);
      assert.equal(currency.formatAmount(1697400, code, locale, { maximumFractionDigits: 0 }), expected);
      assert.equal(mortgage.formatCurrency(1697400, locale, code), expected);
    }
  }
  assert.equal(mortgage.formatCurrency(null), '—');
  assert.equal(currency.applicationCurrency({}), 'EUR');
});

test('reference currency persistence is independent of locale and both theme cookies', () => {
  const filename = path.join(srcDir, 'lib', 'CurrencyProvider.tsx');
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  });
  for (const initialCurrency of currency.CURRENCIES) {
    const state = [];
    const document = {};
    const sourceModule = { exports: {} };
    vm.runInNewContext(outputText, {
      module: sourceModule, exports: sourceModule.exports, document,
      require: name => name === 'react'
        ? { ...React, useState: initial => [initial, next => state.push(next)], useCallback: fn => fn }
        : name === '@/lib/currency' ? currency : require(name),
    });
    const element = sourceModule.exports.CurrencyProvider({ initialCurrency, children: null });
    assert.equal(element.props.value.currency, initialCurrency);
    element.props.value.setCurrency('USD');
    assert.equal(document.cookie, 'reference-currency=USD;path=/;max-age=31536000;samesite=lax');
    assert.deepEqual(state, ['USD']);
    assert.deepEqual(Object.keys(document), ['cookie']);
  }
  const layout = fs.readFileSync(path.join(srcDir, 'app', 'layout.tsx'), 'utf8');
  assert.match(layout, /resolveReferenceCurrency\(cookieStore\.get\(CURRENCY_COOKIE\)\?\.value\)/);
  assert.match(layout, /<CurrencyProvider initialCurrency=\{currency\}>/);
});
