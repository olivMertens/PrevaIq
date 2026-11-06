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
    if (name === '@/lib/brand') return { brand: { primary: '#17395C' } };
    if (name.startsWith('@/lib/')) return load(`${name.slice('@/lib/'.length)}.ts`, libDir);
    return require(name);
  };
  vm.runInThisContext(`(function(module, exports, require) { ${outputText}\n})`, { filename })(module, module.exports, requireComponent);
  return module.exports.default;
}

function elements(node) {
  if (!React.isValidElement(node)) return [];
  return [node, ...React.Children.toArray(node.props.children).flatMap(elements)];
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

test('Aurora is visible when disabled or without a location, without a fabricated graph or enabled launch action', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const states = [{ enabled: false, configured: false }, null, null, false, false];
    let index = 0;
    const AuroraRiskPanel = component(path.join('case', 'AuroraRiskPanel.tsx'), locale, {
      react: { ...React, useState: () => [states[index++], () => {}] },
      '@/lib/api': { APIError: Error },
      './caseUi': { CockpitCard: ({ title, children }) => React.createElement('section', null, title, children) },
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
      useState: () => {
        const key = index++;
        return [state[key], value => { state[key] = typeof value === 'function' ? value(state[key]) : value; }];
      },
    },
  });
  const tree = CommunicationGenerator({ applicationId: 'case-1', insuredName: 'Demo', claimReference: 'DEMO' });
  const nodes = elements(tree);
  const body = nodes.find(node => node.type === 'textarea');
  assert.equal(body.props['aria-label'], messages('en').communicationGenerator.draftBody);
  body.props.onChange({ target: { value: 'Reviewed draft' } });
  assert.equal(state[2].body, 'Reviewed draft');
  nodes.find(node => node.type === 'input').props.onChange({ target: { value: 'Reviewed subject' } });
  assert.equal(state[2].subject, 'Reviewed subject');
});
