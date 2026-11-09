const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { createTranslator } = require('use-intl/core');
const { load, srcDir } = require('./loadTs');
const { neutral, palettes, contrast } = require('../theme.cjs');

const libDir = path.join(srcDir, 'lib');
const workspace = load('claimsWorkspace.ts', libDir);
const urls = load('caseUrl.ts', libDir);
const decisions = load('decisionStyles.ts', path.join(srcDir, 'components', 'case'));
const messages = (locale) => JSON.parse(fs.readFileSync(path.join(srcDir, '..', 'messages', `${locale}.json`), 'utf8'));
const empty = () => null;

function component(relativePath, locale = 'en', stubs = {}) {
  const filename = path.join(srcDir, 'components', relativePath);
  const source = fs.readFileSync(filename, 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  const module = { exports: {} };
  const requireComponent = (name) => {
    if (Object.hasOwn(stubs, name)) return stubs[name];
    if (name === 'next-intl') return {
      useLocale: () => locale,
      useTranslations: (namespace) => createTranslator({ locale, messages: messages(locale), namespace }),
    };
    if (name === '@/lib/ToastProvider') return { useToast: () => ({ addToast() {} }) };
    if (name === './decisionStyles') return decisions;
    if (name === '../claims/sentimentTone') return load('sentimentTone.ts', path.join(srcDir, 'components', 'claims'));
    if (name === '@/lib/brand') return { brand: { primary: '#17395C' } };
    if (name.startsWith('@/lib/')) return load(`${name.slice('@/lib/'.length)}.ts`, libDir);
    return require(name);
  };
  vm.runInThisContext(`(function(module, exports, require) { ${outputText}\n})`, { filename })(module, module.exports, requireComponent);
  return module.exports.default;
}

function elements(node) {
  if (!React.isValidElement(node)) return [];
  return [node, ...React.Children.toArray(node.props.children).flatMap(elements),
    ...React.Children.toArray(node.props.aside).flatMap(elements)];
}

test('claims use six ordered business views and every detail has one primary destination', () => {
  assert.deepEqual(workspace.CLAIM_VIEWS, ['overview', 'documents', 'analysis', 'customer', 'weather', 'timeline']);
  assert.deepEqual(workspace.ANALYSIS_SECTIONS, ['summary', 'cover', 'fraud', 'web']);
  const expected = {
    summary: 'analysis', cover: 'analysis', fraud: 'analysis', web: 'analysis',
    evidence: 'documents', customer: 'customer', timeline: 'timeline', data: 'data', pipeline: 'pipeline',
  };
  for (const [detail, view] of Object.entries(expected)) assert.equal(workspace.claimViewForDetail(detail), view);
  for (const persona of ['habitation_claims', 'property_casualty_claims', 'automotive_claims']) assert.equal(workspace.isClaimsWorkspace(persona), true);
  for (const persona of ['underwriting', 'life_health_claims', 'mortgage']) assert.equal(workspace.isClaimsWorkspace(persona), false);
  for (const view of [...workspace.CLAIM_VIEWS, 'data', 'pipeline', 'source']) {
    const query = urls.withCaseParams('?app=case-1&persona=habitation_claims', { view, page: view === 'source' ? 3 : null });
    const restored = urls.readCaseParams(query);
    assert.equal(restored.view, view);
    assert.equal(restored.app, 'case-1');
    assert.equal(restored.page, view === 'source' ? 3 : null);
  }
});

test('saved fraud is restored only from a completed, structurally usable result', () => {
  assert.equal(workspace.savedClaimFraud(null), null);
  assert.equal(workspace.savedClaimFraud({ fraud_analysis: {} }), null);
  const saved = { application_id: 'case-1', analysis_timestamp: '2026-11-06T12:00:00Z', image_analyses: [], overall_assessment: { overall_fraud_risk: 'HIGH' } };
  assert.equal(workspace.savedClaimFraud({ fraud_analysis: saved }), saved);
});

test('customer drafts follow the human decision, never completed tasks or an AI recommendation', () => {
  assert.equal(workspace.claimCommunicationStatus(null), 'pending');
  assert.equal(workspace.claimCommunicationStatus({ llm_outputs: { recommendation: { decision: 'approve' } } }), 'pending');
  for (const [decision, expected] of [['approve', 'approved'], ['decline', 'denied'], ['approve_with_conditions', 'pending'], ['defer', 'pending'], ['unknown', 'pending']]) {
    assert.equal(workspace.claimCommunicationStatus({ llm_outputs: { decision: { decision } } }), expected);
  }
});

test('fraud launch takes one action; viewing an existing report never starts another run', () => {
  const FraudTab = component(path.join('claims', 'property', 'FraudTab.tsx'), 'fr', {
    '@/components/case/caseUi': { SEVERITY_STYLE: {}, SeverityIcon: empty },
  });
  let runs = 0;
  let reports = 0;
  const props = { running: false, progress: 0, onRun: () => { runs++; }, onOpenReport: () => { reports++; } };
  const initial = elements(FraudTab({ ...props, result: null })).filter(node => node.type === 'button');
  assert.equal(initial.length, 1);
  initial[0].props.onClick();
  assert.equal(runs, 1);
  assert.equal(reports, 0);
  const saved = { overall_assessment: { overall_fraud_risk: 'HIGH', risk_score: 0.76 } };
  const actions = elements(FraudTab({ ...props, result: saved })).filter(node => node.type === 'button');
  actions[0].props.onClick();
  assert.equal(reports, 1);
  assert.equal(runs, 1);
  actions[1].props.onClick();
  assert.equal(runs, 2);
  const running = elements(FraudTab({ ...props, result: null, running: true })).find(node => node.type === 'button');
  assert.equal(running.props.disabled, true);
});

test('decision options are colored before selection and confirmation names the human decision in all locales', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const DecisionDialog = component(path.join('case', 'DecisionDialog.tsx'), locale);
    const html = renderToStaticMarkup(React.createElement(DecisionDialog, {
      applicationId: 'case-1', open: true, onClose() {}, onSubmitted() {},
    }));
    for (const color of ['emerald', 'amber', 'slate', 'rose']) assert.ok(html.includes(`border-${color}-`));
    assert.equal((html.match(/role="radio"/g) || []).length, 4);
    assert.equal((html.match(/aria-checked="false"/g) || []).length, 4);
    const selected = renderToStaticMarkup(React.createElement(DecisionDialog, {
      applicationId: 'case-1', open: true, draft: { decision: 'decline' }, onClose() {}, onSubmitted() {},
    }));
    const t = createTranslator({ locale, messages: messages(locale), namespace: 'caseCockpit.decision' });
    assert.ok(selected.includes(t('confirm', { decision: messages(locale).decisions.decline })));
    assert.ok(selected.includes('bg-rose-700'));
    assert.equal((selected.match(/aria-checked="true"/g) || []).length, 1);
  }
});

test('overview routes coverage to cover, exposes Web IQ, and launches new fraud directly', () => {
  const VerdictBar = component(path.join('case', 'VerdictBar.tsx'));
  let target;
  let runs = 0;
  const tree = VerdictBar({
    identity: [], recommendation: null, criticalCount: 0, analysisRunning: false,
    amount: { label: '100 CHF', expertRequired: false }, fraud: { state: 'none' },
    cover: [], customer: { level: null }, onOpenTab: tab => { target = tab; },
    onRunFraud: () => { runs++; }, onValidate() {}, onOtherDecision() {}, onWhy() {}, onRunAnalysis() {},
  });
  const tiles = elements(tree).filter(node => typeof node.type === 'function' && node.type.name === 'Tile');
  assert.equal(tiles.length, 5);
  tiles.find(node => node.props.label === 'Cover').props.onClick();
  assert.equal(target, 'cover');
  tiles.find(node => node.props.label === 'Web IQ check').props.onClick();
  assert.equal(target, 'web');
  tiles.find(node => node.props.label === 'Fraud risk').props.onClick();
  assert.equal(runs, 1);
});

test('overview KPI backgrounds and icons follow urgency without treating source counts as coverage', () => {
  const VerdictBar = component(path.join('case', 'VerdictBar.tsx'));
  const defaults = {
    identity: [], recommendation: null, criticalCount: 0, analysisRunning: false,
    amount: { label: null, expertRequired: false, thresholdLabel: 'CHF 5’000' },
    fraud: { state: 'none' }, cover: [], customer: { level: null },
    onOpenTab() {}, onRunFraud() {}, onValidate() {}, onOtherDecision() {}, onWhy() {}, onRunAnalysis() {},
  };
  const scenarios = [
    [{}, ['neutral', 'neutral', 'neutral', 'neutral', 'neutral']],
    [{
      amount: { label: 'CHF 14’968’600', expertRequired: true, thresholdLabel: 'CHF 5’000' },
      fraud: { state: 'done', score: 76, band: 'HIGH', siu: true },
      cover: [{ label: 'Event confirmed', status: 'ok' }, { label: 'DDE', status: 'neutral' }],
      web: { source_urls: ['https://example.test/evidence'] },
      customer: { level: 'critical', score: 92 },
    }, ['warning', 'critical', 'info', 'info', 'critical']],
    [{
      amount: { label: 'CHF 100', expertRequired: false },
      fraud: { state: 'done', score: 12, band: 'LOW' },
      cover: [{ label: 'Event confirmed', status: 'ok' }],
      customer: { level: 'calm', score: 10 },
    }, ['info', 'success', 'info', 'neutral', 'success']],
    [{
      amount: { label: 'CHF 10’000', expertRequired: true, overclaimPercent: 20, thresholdLabel: 'CHF 5’000' },
      fraud: { state: 'done', score: 40, band: 'MODERATE' },
      cover: [{ label: 'Review needed', status: 'warning' }],
      web: { error: 'unavailable', source_urls: ['https://example.test/evidence'] },
      customer: { level: 'stressed', score: 55 },
    }, ['critical', 'warning', 'warning', 'warning', 'warning']],
    [{
      fraud: { state: 'running', progress: 30, band: 'HIGH' },
      cover: [{ label: 'Confirmed', status: 'ok' }, { label: 'Excluded', status: 'critical' }],
      customer: { level: 'moderate', score: 80 },
    }, ['neutral', 'running', 'critical', 'neutral', 'critical']],
    [{ fraud: { state: 'done', band: 'LOW', score: 10, siu: true } }, ['neutral', 'critical', 'neutral', 'neutral', 'neutral']],
    [{ customer: { level: null, score: 99 } }, ['neutral', 'neutral', 'neutral', 'neutral', 'neutral']],
  ];
  const colors = { critical: 'rose', warning: 'amber', success: 'emerald', info: 'sky', running: 'violet', neutral: 'slate' };
  for (const [overrides, expected] of scenarios) {
    const tree = VerdictBar({ ...defaults, ...overrides });
    const tiles = elements(tree).filter(node => typeof node.type === 'function' && node.type.name === 'Tile');
    assert.deepEqual(tiles.map(tile => tile.props.tone), expected);
    tiles.forEach((tile, index) => {
      const rendered = tile.type(tile.props);
      assert.match(rendered.props.className, new RegExp(`bg-${colors[expected[index]]}-50/`));
      assert.match(rendered.props.className, new RegExp(`border-${colors[expected[index]]}-`));
      const header = elements(rendered).find(node => node.type === 'span');
      assert.match(header.props.className, new RegExp(`text-${colors[expected[index]]}-`));
      assert.ok(renderToStaticMarkup(rendered).includes('<svg'), 'context icon must remain visible');
      const background = rendered.props.className.match(/\bbg-(\w+)-(\d+)\/(\d+)/);
      const hover = rendered.props.className.match(/\bhover:bg-(\w+)-(\d+)\/(\d+)/);
      const composite = (foreground, parent, opacity) => {
        const rgb = color => color.match(/[a-f\d]{2}/gi).map(channel => parseInt(channel, 16));
        const base = rgb(parent);
        return '#' + rgb(foreground).map((value, channel) =>
          Math.round(value * opacity + base[channel] * (1 - opacity)).toString(16).padStart(2, '0')
        ).join('');
      };
      for (const theme of ['light', 'dark']) {
        for (const match of [background, hover]) {
          const color = palettes[match[1]][match[2]];
          const surface = composite(theme === 'light' ? color.lightBackground : color.background, theme === 'light' ? '#ffffff' : neutral.surface, Number(match[3]) / 100);
          for (const node of elements(rendered)) {
            for (const text of (node.props.className || '').matchAll(/\btext-(slate|rose|amber|emerald|sky|violet|indigo|purple)-(\d+)\b/g)) {
              const textColor = palettes[text[1]][text[2]];
              assert.ok(contrast(theme === 'light' ? textColor.lightText : textColor.text, surface) >= 4.5, `${tile.props.label}: ${theme} ${text[0]} reading contrast`);
            }
          }
        }
      }
    });
  }
});

test('Aurora is visible when disabled or without a location, without a fabricated graph or enabled launch action', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const AuroraRiskPanel = component(path.join('case', 'AuroraRiskPanel.tsx'), locale, {
      './useAuroraEvidence': { useAuroraEvidence: () => ({
        status: {enabled: false, configured: false}, forecast: null, context: null,
        error: null, initializing: false, setForecast() {},
      }) },
      './CaseTabs': empty,
      './AuroraClaimMetrics': empty,
      '@/lib/api': { APIError: Error },
      './caseUi': { CockpitCard: ({ title, children, aside }) => React.createElement('section', null, title, aside, children) },
      './AuroraForecastChart': () => { throw new Error('Disabled Aurora must not render a forecast chart'); },
      './AuroraStormTimeline': { default: () => { throw new Error('Disabled Aurora must not render a weather timeline'); }, AuroraResolvingState: empty, __esModule: true },
      '@/components/aurora/AuroraExpiryCountdown': empty,
    });

    const html = renderToStaticMarkup(React.createElement(AuroraRiskPanel, { applicationId: 'case-1' }));
    assert.ok(html.includes(messages(locale).caseCockpit.aurora.disabled));
    assert.ok(html.includes(messages(locale).caseCockpit.aurora.locationRequired));
    assert.ok(html.includes('role="status"'));
    const buttons = html.match(/<button\b[^>]*>/g) || [];
    assert.ok(buttons.every(button => button.includes('disabled=""')));
  }
});

test('claims demo guidance mirrors all six navigation labels and keeps Aurora availability explicit', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const m = messages(locale);
    for (const view of workspace.CLAIM_VIEWS) assert.ok(m.demoGuide.claimsNavigation.includes(m.nav.claims[view]), `${locale}: ${view}`);
    for (const id of ['habitation-ch', 'habitation-ch-watch']) {
      assert.ok(m.demoGuide.scenarios[id].steps[2].detail.includes(m.nav.claims.documents));
    }
    assert.ok(m.demoGuide.scenarios.habitation.steps[3].detail.includes(m.nav.claims.weather));
  }
});

test('Aurora date alignment distinguishes a calendar day from a timezone-qualified instant', () => {
  const {parseAuroraClaimTime: parse} = load('auroraClaimTime.ts', libDir);
  for (const date of ['2026-08-28', '28/08/2026', '28.08.2026']) {
    const interval = parse(date);
    assert.equal(interval.precision, 'day');
    assert.ok(interval.end > interval.start);
    assert.ok(interval.marker >= interval.start && interval.marker <= interval.end);
  }
  assert.equal(parse('2026-08-28T09:00:00+02:00').start, Date.parse('2026-08-28T07:00:00Z'));
  for (const date of ['31/02/2026', '2026-02-31', '2026-08', '2026', '2026-08-28T07:00:00', 'unknown']) {
    assert.equal(parse(date), null, date);
  }
});

test('case analysis mounts just one section', () => {
  const CaseTabs = component(path.join('case', 'CaseTabs.tsx'));
  const Analysis = component(path.join('case', 'ClaimAnalysisSections.tsx'), 'en', {'./CaseTabs': CaseTabs});
  for (const focus of [undefined, 'cover', 'fraud', 'web']) {
    const rendered = [];
    const html = renderToStaticMarkup(React.createElement(Analysis, {
      focus, renderSection: section => { rendered.push(section); return React.createElement('p', null, section); },
    }));
    assert.deepEqual(rendered, [focus ?? 'summary']);
    assert.equal((html.match(/role="tabpanel"/g) || []).length, 1);
    assert.equal((html.match(/role="tab"/g) || []).length, 4);
  }
});

test('case tabs support arrows, Home, End and roving focus', () => {
  const Tabs = component(path.join('case', 'CaseTabs.tsx'), 'en', {
    react: {...React, useRef: () => ({current: {}})},
  });
  const changed = [], focused = [];
  const tree = Tabs({tabs: ['aurora', 'location', 'web'].map(id => ({id, label: id})),
    active: 'aurora', idPrefix: 'test-tabs', label: 'test', onChange: id => changed.push(id)});
  const buttons = elements(tree).filter(node => node.type === 'button');
  buttons.forEach(button => button.props.ref({focus: () => focused.push(button.props.id)}));
  assert.deepEqual(buttons.map(button => button.props.tabIndex), [0, -1, -1]);
  for (const key of ['ArrowRight', 'End', 'Home', 'ArrowLeft']) {
    buttons[0].props.onKeyDown({key, preventDefault() {}});
  }
  assert.deepEqual(changed, ['location', 'web', 'aurora', 'web']);
  assert.deepEqual(focused, changed.map(id => `test-tabs-${id}-tab`));
});

test('saved summary shows model risks and review preparation even if availability lookup fails', () => {
  const Summary = component(path.join('case', 'AuroraEvidenceSummary.tsx'), 'en', {
    './useAuroraEvidence': {useAuroraEvidence: () => ({
      status: null, error: 'statusError', initializing: false,
      forecast: {
        forecast: {max_wind_gust_ms: 9.7, total_precipitation_mm: 3.359},
        decision_support: {severity: 'low', recommended_actions: ['verify_claim_evidence']},
      },
      context: {kind: 'historical_simulation', point_count: 2,
        window: {starts_at: '2026-08-28T07:00:00Z', ends_at: '2026-08-28T08:00:00Z'}},
    })},
  });
  const html = renderToStaticMarkup(React.createElement(Summary, {applicationId: 'saved-case'}));
  for (const text of ['role="alert"', 'Historical simulation', '9.7', '2026', 'Model weather signal', 'Prepare customer contact']) {
    assert.ok(html.includes(text), text);
  }
});

test('forecast failures show a localized toast and retain saved evidence', async () => {
  const toasts = [], writes = [];
  let requestCount = 0;
  const Panel = component(path.join('case', 'AuroraRiskPanel.tsx'), 'fr', {
    react: {...React, useState: initial => [initial, () => {}]},
    '@/lib/api': {APIError: class APIError extends Error {}, createAuroraForecast: async () => {
      requestCount++;
      throw new Error('PRIVATE_SERVER_ERROR_MUST_NOT_BE_SHOWN');
    }},
    '@/lib/ToastProvider': {useToast: () => ({addToast: (...args) => toasts.push(args)})},
    './useAuroraEvidence': {useAuroraEvidence: () => ({
      status: {enabled: true, configured: true, default_horizon_hours: 6},
      forecast: null, context: null, error: null, initializing: false, setForecast: value => writes.push(value),
    })},
    './caseUi': {CockpitCard: ({children}) => React.createElement('section', null, children)},
    './CaseTabs': empty, './AuroraForecastChart': empty, './AuroraClaimMetrics': empty,
    './AuroraStormTimeline': {default: empty, AuroraResolvingState: empty, __esModule: true},
    '@/components/aurora/AuroraExpiryCountdown': empty,
  });
  const tree = Panel({applicationId: 'saved-case', latitude: 46.2, longitude: 6.1});
  assert.equal(requestCount, 0);
  await elements(tree).find(node => node.type === 'button').props.onClick();
  assert.equal(requestCount, 1);
  assert.deepEqual(toasts, [['error', messages('fr').caseCockpit.aurora.error]]);
  assert.deepEqual(writes, []);
});

test('Web IQ action explicitly describes the coupled fraud run and surfaces failures', () => {
  const WebCheck = component(path.join('claims', 'property', 'WebCheckTab.tsx'));
  let runs = 0;
  const tree = WebCheck({ web: null, onRun: () => { runs++; } });
  const button = elements(tree).find(node => node.type === 'button');
  assert.ok(renderToStaticMarkup(tree).includes(messages('en').caseCockpit.webTab.integratedCheck));
  button.props.onClick();
  assert.equal(runs, 1);
  const failed = renderToStaticMarkup(WebCheck({ web: { error: 'unavailable' } }));
  assert.ok(failed.includes('role="alert"'));
  assert.ok(failed.includes(messages('en').caseCockpit.webTab.error));
});

test('customer message body and subject are editable drafts, not an automatic send action', () => {
  const state = ['email', 'empathetic', { type: 'email', tone: 'empathetic', subject: 'Initial subject', body: 'Initial draft' }, false, false, false, null];
  let index = 0;
  const CommunicationGenerator = component(path.join('claims', 'CommunicationGenerator.tsx'), 'en', {
    react: {
      ...React, useCallback: callback => callback,
      useEffect: () => {}, useRef: () => ({ current: null }),
      useState: () => {
        const key = index++;
        return [state[key], value => { state[key] = typeof value === 'function' ? value(state[key]) : value; }];
      },
    },
  });
  const composer = CommunicationGenerator({ applicationId: 'case-1', insuredName: 'Demo', claimReference: 'DEMO' });
  const tree = composer.type(composer.props);
  const nodes = elements(tree);
  const body = nodes.find(node => node.type === 'textarea');
  assert.equal(body.props['aria-label'], messages('en').communicationGenerator.draftBody);
  body.props.onChange({ target: { value: 'Reviewed draft' } });
  assert.equal(state[2].body, 'Reviewed draft');
  nodes.find(node => node.type === 'input').props.onChange({ target: { value: 'Reviewed subject' } });
  assert.equal(state[2].subject, 'Reviewed subject');
});
