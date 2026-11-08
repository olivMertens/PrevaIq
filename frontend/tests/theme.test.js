const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const React = require('react');
const ts = require('typescript');
const postcss = require('postcss');
const tailwind = require('tailwindcss');
const { neutral, palettes, contrast } = require('../theme.cjs');
const { load, srcDir } = require('./loadTs');
const themes = load('theme.ts', path.join(srcDir, 'lib'));

test('both theme names are explicit and unknown persisted values resolve to light', () => {
  for (const [value, expected] of [['dark', 'dark'], ['light', 'light'], [undefined, 'light'], ['invalid', 'light']]) {
    assert.equal(themes.resolveAppTheme(value), expected);
  }
});

test('theme changes update the full-document cookie and colors without a reload or touching the locale', () => {
  const filename = path.join(srcDir, 'lib', 'ThemeProvider.tsx');
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  });
  for (const initialTheme of ['light', 'dark']) {
    const state = [];
    const document = { documentElement: { dataset: { appTheme: initialTheme }, style: { colorScheme: initialTheme }, lang: 'de-CH' } };
    const sourceModule = { exports: {} };
    vm.runInNewContext(outputText, {
      module: sourceModule, exports: sourceModule.exports, document,
      require: name => name === 'react'
        ? { ...React, useState: initial => [initial, next => state.push(next)], useCallback: fn => fn }
        : name === '@/lib/theme' ? themes : require(name),
    });
    const element = sourceModule.exports.ThemeProvider({ initialTheme, children: null });
    const next = initialTheme === 'light' ? 'dark' : 'light';
    element.props.value.setTheme(next);
    assert.equal(document.cookie, `app-theme=${next};path=/;max-age=31536000;samesite=lax`);
    assert.equal(document.documentElement.dataset.appTheme, next);
    assert.equal(document.documentElement.style.colorScheme, next);
    assert.equal(document.documentElement.lang, 'de-CH');
    assert.deepEqual(state, [next]);
  }
});

test('every dark reading palette exceeds WCAG AA text contrast and solid actions retain white text', () => {
  assert.ok(contrast(neutral.text, neutral.surface) >= 7);
  assert.ok(contrast(neutral.muted, neutral.surface) >= 4.5);
  for (const [name, shades] of Object.entries(palettes)) {
    for (const [shade, values] of Object.entries(shades)) {
      assert.ok(contrast(values.text, values.background) >= 4.5, `${name}-${shade}: reading contrast`);
      assert.ok(contrast(values.text, neutral.surface) >= 4.5, `${name}-${shade}: card text contrast`);
      if (Number(shade) >= 500) {
        assert.ok(contrast('#ffffff', values.background) >= 4.5, `${name}-${shade}: action contrast`);
      }
    }
  }
});

test('generated theme CSS covers hover, focus, selected tabs, opacity, gradients and placeholders', async () => {
  const config = require('../tailwind.config');
  const result = await postcss([tailwind({
    ...config,
    content: [{ raw: 'bg-white bg-white/80 text-slate-500 border-slate-200 hover:bg-slate-50 focus:bg-slate-100 aria-pressed:bg-slate-100 from-slate-50 via-white to-indigo-50/30 placeholder-slate-400 divide-slate-200 text-rose-900 bg-rose-50 bg-rose-700', extension: 'html' }],
  })]).process('@tailwind utilities;', { from: undefined });
  for (const part of [
    'data-app-theme="dark"', 'data-theme-static', '.hover\\:bg-slate-50:hover',
    '.focus\\:bg-slate-100:focus', '.bg-white\\/80', '::placeholder',
    '--tw-gradient-from', '--tw-gradient-stops', '--tw-gradient-to',
  ]) assert.ok(result.css.includes(part), part);
  assert.ok(result.css.includes(neutral.surface));
  assert.doesNotMatch(result.css, /\bfilter:|invert\(/);
});

test('light muted labels and status text remain readable on their light surfaces', () => {
  for (const [family, shades] of Object.entries(palettes)) {
    const targets = ['slate', 'gray', 'zinc', 'neutral', 'stone'].includes(family) ? [400] : [400, 500, 600, 700];
    for (const shade of targets) {
      assert.ok(contrast(shades[shade].lightText, shades[50].lightBackground) >= 4.5, `${family}-${shade}`);
    }
  }
});

test('health header reading labels meet text contrast on both ends of its gradient', () => {
  const colors = require('tailwindcss/colors');
  for (const background of [colors.indigo[600], colors.indigo[700]]) {
    for (const text of [colors.indigo[100], colors.emerald[100], '#ffffff']) {
      assert.ok(contrast(text, background) >= 4.5);
    }
  }
  const source = fs.readFileSync(path.join(srcDir, 'components', 'claims', 'LifeHealthHeaderStrip.tsx'), 'utf8');
  assert.doesNotMatch(source, /text-indigo-200|text-emerald-300/);
});
test('every account appearance label exists in all locales and deployment copies the shared palette', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const labels = require(`../messages/${locale}.json`).appearance;
    for (const key of ['title', 'light', 'dark']) assert.equal(typeof labels[key], 'string', `${locale}.${key}`);
  }
  const read = relative => fs.readFileSync(path.resolve(__dirname, '..', relative), 'utf8');
  assert.match(read('Dockerfile'), /COPY .*theme\.cjs/);
  assert.match(read('..\\infra\\deploy.ps1'), /Copy-Item "\$FrontendDir\\theme\.cjs"/);
  const layout = read('src\\app\\layout.tsx');
  assert.match(layout, /cookies\(\)/);
  assert.match(layout, /data-app-theme=\{theme\}/);
  assert.match(layout, /<ThemeProvider initialTheme=\{theme\}>/);
  assert.match(read('src\\components\\UserMenu.tsx'), /<ThemeToggle menu/);
});
