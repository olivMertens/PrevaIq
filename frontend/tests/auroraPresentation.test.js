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
const {swissGermanMessages} = load('locales.ts', path.join(srcDir, 'i18n'));

const initial = '2026-08-28T06:00:00Z';
const evidence = {
  request_id: 'preserved-request',
  model: 'prevaiq-synthetic-weather-v1',
  requested_at: '2026-11-09T06:00:00Z',
  latitude: 47.49, longitude: 8.72, horizon_hours: 6, ensemble: false,
  forecast: {
    series: Array.from({length: 6}, (_, i) => ({
      valid_at: new Date(Date.parse(initial) + (i + 1) * 3600000).toISOString(),
      temperature_c: 20 - i, wind_speed_ms: 10, wind_gust_ms: 25,
      precipitation_mm: 6, snowfall_mm: 0, cloud_cover_percent: 95,
    })),
    max_wind_gust_ms: 25, max_wind_speed_ms: 10, total_precipitation_mm: 36,
  },
  decision_support: {
    severity: 'high', human_review_required: true, advisory_only: true,
    hazard_window: {starts_at: '2026-08-28T07:00:00Z', ends_at: '2026-08-28T12:00:00Z'},
    recommended_actions: ['preserve_evidence'], customer_talking_points: ['photos_before_repairs'],
  },
  provenance: {
    source: 'demo_simulation', synthetic: true, provider: 'PrevaIQ demo',
    scenario_id: 'swiss-chocolate-storm', scenario_started_at: initial,
  },
};

function render(filename, locale, {states = [], props = {}, saved = true} = {}) {
  let stateIndex = 0;
  const cache = new Map();
  const raw = JSON.parse(fs.readFileSync(
    path.join(srcDir, '..', 'messages', `${locale === 'de-CH' ? 'de' : locale}.json`), 'utf8',
  ));
  const messages = locale === 'de-CH' ? swissGermanMessages(raw) : raw;
  function moduleAt(file) {
    if (cache.has(file)) return cache.get(file);
    const sourceModule = {exports: {}};
    cache.set(file, sourceModule.exports);
    const {outputText} = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
      },
    });
    const localRequire = specifier => {
      if (specifier === 'react') return {
        ...React,
        useState: initialValue => {
          const index = stateIndex++;
          return [index in states ? states[index] : initialValue, () => {}];
        },
        useEffect: () => {}, useMemo: fn => fn(), useRef: () => ({current: null}),
      };
      if (specifier === 'next-intl') return {
        useLocale: () => locale,
        useTranslations: namespace => createTranslator({
          locale, messages, namespace, onError: error => { throw error; },
        }),
      };
      if (specifier === './useAuroraEvidence') return {
        useAuroraEvidence: () => ({
          status: {enabled: true, configured: true, mode: 'demo_simulation'},
          forecast: saved ? evidence : null,
          context: saved ? {
            kind: 'demo_simulation', point_count: 6,
            window: evidence.decision_support.hazard_window,
          } : null,
          initializing: false, error: null,
        }),
      };
      if (specifier === '@/lib/ToastProvider') return {useToast: () => ({addToast: () => {}})};
      if (specifier === '@/lib/api') return {APIError: class extends Error {}};
      if (specifier.startsWith('@/') || specifier.startsWith('.')) {
        const base = specifier.startsWith('@/') ? path.join(srcDir, specifier.slice(2))
          : path.resolve(path.dirname(file), specifier);
        const target = ['.tsx', '.ts'].map(ext => `${base}${ext}`).find(p => fs.existsSync(p));
        if (!target) throw new Error(`Unknown source import: ${specifier}`);
        return moduleAt(target);
      }
      return require(specifier);
    };
    vm.runInThisContext(`(function(module,exports,require){${outputText}\n})`, {filename: file})(
      sourceModule, sourceModule.exports, localRequire,
    );
    return sourceModule.exports;
  }
  const Component = moduleAt(path.join(srcDir, ...filename.split('/'))).default;
  return {html: renderToStaticMarkup(React.createElement(Component, props)), messages};
}

for (const locale of ['en', 'fr', 'de', 'de-CH']) {
  test(`${locale}: customer outlook tabs and summary show no implementation-mode labels`, () => {
    const original = JSON.stringify(evidence);
    for (const tab of ['chart', 'timeline', 'trace', 'actions']) {
      const {html} = render('components/case/AuroraRiskPanel.tsx', locale, {
        states: [null, false, tab], props: {applicationId: 'case', latitude: 47.49, longitude: 8.72},
      });
      assert.doesNotMatch(html, /demo|démo|simulat|synthe|synthé/i, `${locale}.${tab}`);
      assert.ok(html.includes('25'), 'Outlook metrics should still be rendered');
      assert.doesNotMatch(html, /Microsoft Foundry|prevaiq-synthetic-weather-v1/);
      assert.match(html, /<details class="/, 'Weather details should be collapsed by default');
      assert.doesNotMatch(html, /<details[^>]*\bopen(?:=|\s|>)/);
    }
    const {html, messages} = render('components/case/AuroraEvidenceSummary.tsx', locale, {
      props: {applicationId: 'case'},
    });
    assert.doesNotMatch(html, /demo|démo|simulat|synthe|synthé/i);
    assert.ok(!html.includes(messages.caseCockpit.aurora.summary.risk.split('{')[0]));
    const empty = render('components/case/AuroraRiskPanel.tsx', locale, {
      saved: false, props: {applicationId: 'case'},
    });
    assert.ok(empty.html.includes(empty.messages.caseCockpit.aurora.scenario.run));
    assert.ok(empty.html.includes(empty.messages.caseCockpit.aurora.claimMetrics.generate));
    assert.equal(JSON.stringify(evidence), original, 'Presentation must not rewrite provenance');
  });

  test(`${locale}: administration retains explicit simulation controls, audit and guide`, () => {
    const {html, messages} = render('components/admin/AuroraDemoSettings.tsx', locale, {
      props: {
        enabled: true, scenario: 'swiss-chocolate-storm', disabled: false,
        validatedAt: '2026-11-09', validatedBy: 'verified-admin',
        liveConfigured: false, onEnabledChange() {}, onScenarioChange() {}, onSave() {},
      },
    });
    assert.ok(html.includes(messages.auroraDemo.title));
    assert.ok(html.includes('verified-admin'));
    assert.ok(html.includes('2026-11-09'));
    const presentation = renderToStaticMarkup(React.createElement(
      React.Fragment, null, messages.auroraDemo.presentation,
    ));
    assert.ok(html.includes(presentation));
    assert.ok(html.includes(messages.auroraDemo.guideTitle));
    assert.ok(html.includes(messages.auroraDemo.saveMode));
    assert.match(html, /simulat/i);
    for (const id of ['habitation', 'habitation-ch', 'habitation-ch-watch']) {
      const detail = messages.demoGuide.scenarios[id].steps[3].detail;
      assert.ok(!detail.includes(messages.auroraDemo.guide));
      assert.doesNotMatch(detail, /demo_simulation|synthetic results|résultats synthétiques|synthetische Ergebnisse/i);
    }
  });

  test(`${locale}: compact claim metrics convert gusts and warn on a mismatching loss date`, () => {
    const {html, messages} = render('components/case/AuroraClaimMetrics.tsx', locale, {
      props: {forecast: evidence.forecast, claimDate: '2030-01-01'},
    });
    assert.ok(html.includes('90 km/h'));
    assert.ok(html.includes(messages.caseCockpit.aurora.claimMetrics.scope.outside_window));
    const boundary = renderToStaticMarkup(React.createElement(React.Fragment, null,
      messages.caseCockpit.aurora.claimMetrics.scopeHelp.outside_window));
    assert.ok(html.includes(boundary));
    assert.doesNotMatch(html, /demo|démo|simulat|synthe|synthé/i);
  });
}
