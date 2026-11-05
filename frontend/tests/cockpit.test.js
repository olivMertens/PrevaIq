const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const caseDir = path.resolve(__dirname, '..', 'src', 'components', 'case');
const libDir = path.resolve(__dirname, '..', 'src', 'lib');

function load(name, dir = caseDir) {
  const filename = path.join(dir, name);
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const sourceModule = { exports: {} };
  // Same realm as the test, so deepStrictEqual compares plain arrays and objects.
  vm.runInThisContext(`(function (module, exports) {${outputText}\n})`, { filename })(
    sourceModule,
    sourceModule.exports,
  );
  return sourceModule.exports;
}

const signals = load('caseSignals.ts');
const updates = load('caseUpdates.ts');
const health = load('pipelineHealth.ts');
const recommendation = load('recommendation.ts');
const currency = load('currency.ts', libDir);
const display = load('applicationDisplay.ts', libDir);

test('long case titles are shown compact, short ones unchanged', () => {
  const { compactApplicationTitle } = display;
  const compact = (title) => compactApplicationTitle(title).text;

  assert.equal(
    compact('Olivier MERTENS LAFFITE — Dégâts des eaux - infiltration suite à tempête'),
    'O. MERTENS LAFFITE · Dégâts des eaux',
  );
  assert.equal(
    compact('MERTENS LAFFITE Olivier — Dégâts des eaux - infiltration suite à tempête'),
    'MERTENS LAFFITE O. · Dégâts des eaux',
  );
  assert.equal(
    compact('Schoggimanufaktur Eulachblick GmbH — Grêle / tempête (dommage élémentaire)'),
    'Schoggimanufaktur Eulachblick · Grêle / tempête',
  );
  assert.equal(compact('RENARD Christophe (flotte SARL Renard Transport)'), 'RENARD Christophe');
  assert.equal(
    compact('Mertens Olivier — Collision / frottement latéral avec bris de glace'),
    'Mertens Olivier · Collision / frottement…',
  );
  assert.equal(compact('Jean-Pierre Marie DUPONT-MOREAU — Vol'), 'J.-P. M. DUPONT-MOREAU · Vol');
  // Not a "given names + SURNAME" shape: left as written.
  assert.equal(compact('Boulangerie DUPONT Frères Rive Gauche'), 'Boulangerie DUPONT Frères Rive…');
  for (const title of ['MARTIN Claire — Dommages structure', 'Priya Patel — Term Life $1M', 'E0FF1B47']) {
    assert.equal(compact(title), title.replace(' — ', ' · '));
  }
  assert.deepEqual(compactApplicationTitle('LECOMTE Sandrine'), {
    holder: 'LECOMTE Sandrine',
    subject: null,
    text: 'LECOMTE Sandrine',
  });
});

test('amounts follow the claim currency (CHF in Switzerland) and the UI language', () => {
  const { applicationCurrency, formatAmount } = currency;
  assert.equal(applicationCurrency({ jurisdiction: { country: 'CH', currency: 'CHF' } }), 'CHF');
  assert.equal(applicationCurrency({ jurisdiction: { country: 'FR', currency: 'EUR' } }), 'EUR');
  assert.equal(applicationCurrency({}), 'EUR');
  assert.equal(applicationCurrency(null), 'EUR');

  for (const locale of ['en', 'fr', 'de']) {
    const chf = formatAmount(1697400, 'CHF', locale, { maximumFractionDigits: 0 });
    assert.match(chf, /CHF/);
    assert.match(chf, /1.697.400/);
    assert.doesNotMatch(chf, /€/);
  }
  assert.match(formatAmount(6560, 'EUR', 'fr', { maximumFractionDigits: 0 }), /6\s?560\s?€/);
  assert.equal(formatAmount(6560, 'EUR', 'en', { maximumFractionDigits: 0 }), '€6,560');
});

test('model findings are filed under a theme in English, French and German', () => {
  const { classifyTheme } = signals;
  assert.equal(classifyTheme('Possibly AI-generated image'), 'photos');
  assert.equal(classifyTheme('Insufficient statement consistency'), 'statement');
  assert.equal(classifyTheme('Chronology to be clarified'), 'timeline');
  assert.equal(classifyTheme('Weather cause not confirmed'), 'cover');
  assert.equal(classifyTheme('Estimated amount to be recontextualized'), 'amount');
  assert.equal(classifyTheme('Exclusions / cover to be checked'), 'policy');
  assert.equal(classifyTheme('Cohérence de la déclaration insuffisante'), 'statement');
  assert.equal(classifyTheme('Montant estimé à recontextualiser'), 'amount');
  assert.equal(classifyTheme('Möglicherweise KI-generiertes Bild'), 'photos');
  assert.equal(classifyTheme('Wetterursache nicht bestätigt'), 'cover');
  assert.equal(classifyTheme('Ausschlüsse und Deckung prüfen'), 'policy');
  assert.equal(classifyTheme('Electrical damage pattern may reflect chronic moisture'), 'fraud');
});

test('duplicate facts merge into one ranked signal that keeps every source', () => {
  const merged = signals.mergeSignals([
    { theme: 'amount', severity: 'warning', title: 'High amount', detail: '€6,560 > €5,000', sources: ['rule'] },
    { theme: 'cover', severity: 'warning', title: 'Weather event', detail: 'Not confirmed', sources: ['rule'] },
    { theme: 'photos', severity: 'critical', title: '1 suspicious photo', detail: '22%', sources: ['photoAnalysis'] },
    { theme: 'cover', severity: 'critical', title: 'Storm not confirmed', detail: '8 sources', sources: ['webIq'], tab: 'web' },
    { theme: 'amount', severity: 'warning', title: 'Amount to recontextualize', detail: 'LLM', sources: ['fraudModel'] },
    { theme: 'fraud', severity: 'warning', title: 'Chronic moisture', detail: 'a', sources: ['fraudModel'] },
    { theme: 'fraud', severity: 'warning', title: 'Infiltration path not evidenced', detail: 'b', sources: ['fraudModel'] },
  ]);

  assert.deepEqual(merged.map((s) => s.title), [
    '1 suspicious photo',
    'Storm not confirmed',
    'High amount',
    'Chronic moisture',
    'Infiltration path not evidenced',
  ]);
  const cover = merged.find((s) => s.theme === 'cover');
  assert.equal(cover.severity, 'critical');
  assert.deepEqual(cover.sources, ['rule', 'webIq']);
  assert.deepEqual(cover.merged, ['Weather event']);
  assert.equal(cover.tab, 'web');
  const amount = merged.find((s) => s.theme === 'amount');
  assert.deepEqual(amount.merged, ['Amount to recontextualize']);
  assert.deepEqual(amount.sources, ['rule', 'fraudModel']);
  assert.equal(new Set(merged.map((s) => s.id)).size, merged.length);
});

test('essential view shows important signals first and hides information-only ones', () => {
  const merged = signals.mergeSignals([
    { theme: 'customer', severity: 'info', title: 'Urgency', detail: '', sources: ['rule'] },
    { theme: 'photos', severity: 'critical', title: 'Photo', detail: '', sources: ['photoAnalysis'] },
    { theme: 'documents', severity: 'warning', title: 'Missing estimate', detail: '', sources: ['rule'] },
  ]);
  const { shown, hidden } = signals.splitEssential(merged, 5);
  assert.deepEqual(shown.map((s) => s.title), ['Photo', 'Missing estimate']);
  assert.deepEqual(hidden.map((s) => s.title), ['Urgency']);
  assert.deepEqual(signals.countByFilter(merged), { all: 3, fraud: 1, cover: 0, amount: 0, documents: 1, customer: 1 });
});

test('latest updates are ordered and only new since the previous visit', () => {
  const list = updates.collectCaseUpdates({
    created_at: '2026-10-16T13:53:34Z',
    files: [1, 2, 3],
    extracted_fields: { a: 1, b: 2 },
    orchestration: {
      stages: { extraction: { completed_at: '2026-10-16T13:55:11Z' }, analysis: { completed_at: '2026-10-16T13:57:41Z' } },
      review: { status: 'needs_review' },
    },
    sentiment_analysis: { computed_at: '2026-10-16T13:57:46Z', level: 'critical', score: 88 },
    fraud_analysis: {
      analysis_timestamp: '2026-10-16T15:01:43Z',
      overall_assessment: { overall_fraud_risk: 'HIGH', risk_score: 0.79, siu_referral_recommended: true },
      web_intelligence: { event_verified: false, source_urls: ['a', 'b'] },
    },
    action_history: [{ action_id: 'x', label: 'Decision: deferred', at: 'not a date', decision: 'defer' }],
  });

  assert.deepEqual(list.map((u) => u.kind), ['fraud', 'webCheck', 'sentiment', 'analysis', 'extraction', 'created']);
  assert.deepEqual(list[0].params, { band: 'HIGH', score: 79, siu: 1 });
  assert.deepEqual(list[1].params, { verdict: 'notConfirmed', sources: 2 });
  assert.deepEqual(list[3].params, { review: 1 });
  const previousVisit = Date.parse('2026-10-16T14:00:00Z');
  assert.deepEqual(list.filter((u) => updates.isNewSince(u, previousVisit)).map((u) => u.kind), ['fraud', 'webCheck']);
  assert.equal(list.some((u) => updates.isNewSince(u, null)), false);
});

test('AI pipeline stays quiet when fine and flags review or real problems', () => {
  assert.equal(health.pipelineHealth({}).status, 'ok');
  const review = health.pipelineHealth({
    orchestration: { review: { status: 'needs_review', reasons: [{ code: 'unverified_llm_fields' }] } },
  });
  assert.deepEqual([review.status, review.reasons], ['review', ['unverified_llm_fields']]);
  const problem = health.pipelineHealth({
    orchestration: {
      stages: { analysis: { budget_exhausted: true } },
      review: { status: 'needs_review', reasons: [{ code: 'low_confidence' }, { code: 'analysis_errors' }] },
    },
  });
  assert.deepEqual([problem.status, problem.reasons], ['problem', ['analysis_errors', 'low_confidence']]);
  const fallback = health.pipelineHealth({ extraction_provenance: { summary: { fallback_used: true, fallback_reason: 'cu_timeout' } } });
  assert.deepEqual([fallback.status, fallback.fallbackReason], ['review', 'cu_timeout']);
  const reviewedFallback = health.pipelineHealth({
    extraction_provenance: { summary: { fallback_used: true, fallback_reason: 'cu_timeout' } },
    orchestration: { review: { status: 'reviewed' } },
  });
  assert.equal(reviewedFallback.status, 'ok');
  assert.equal(health.pipelineHealth({ orchestration: { review: { status: 'reviewed' } } }).status, 'ok');
});

test('recommendations map to real decisions and never invent a confidence score', () => {
  const t = (key, values) => (values ? `${key}:${JSON.stringify(values)}` : key);
  const base = { analysisComplete: true, fraudRisk: 0.1, siuRecommended: false, inconsistentStatement: false, amount: 1200, amountLabel: '1,200' };

  assert.equal(recommendation.buildRecommendation({ ...base, analysisComplete: false }, t), null);
  const siu = recommendation.buildRecommendation({ ...base, siuRecommended: true, fraudRisk: 0.79 }, t);
  assert.deepEqual([siu.id, siu.decision, siu.tone, siu.taskKey], ['escalate_siu', 'defer', 'critical', 'siu_referral']);
  assert.deepEqual([siu.title, siu.reason], ['labels.escalate_siu', 'reasoning.siu_default']);
  assert.equal('confidence' in siu, false);
  assert.equal(recommendation.buildRecommendation({ ...base, fraudRisk: 0.65 }, t).id, 'request_expertise');
  const expert = recommendation.buildRecommendation({ ...base, amount: 6560, amountLabel: '6,560' }, t);
  assert.deepEqual([expert.id, expert.decision], ['approve_with_expertise', 'approve_with_conditions']);
  assert.match(expert.reason, /6,560/);
  assert.deepEqual(
    [recommendation.buildRecommendation(base, t).id, recommendation.buildRecommendation(base, t).decision],
    ['stp_approve', 'approve'],
  );
  assert.equal(recommendation.buildRecommendation({ ...base, fraudRisk: 0.4 }, t).id, 'approve_standard');
});

test('every dynamic cockpit key exists in English, French and German', () => {
  const messagesDir = path.resolve(__dirname, '..', 'messages');
  const lookup = (messages, key) =>
    key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), messages);

  const keys = [
    ...['critical', 'warning', 'info'].map((value) => `caseCockpit.severity.${value}`),
    ...Object.keys(signals.THEME_TAB).map((theme) => `caseCockpit.themes.${theme}`),
    ...['photoAnalysis', 'declarationCheck', 'fraudModel', 'webIq', 'policy', 'rule', 'fileDates', 'aiAnalysis']
      .map((source) => `caseCockpit.sources.${source}`),
    ...['all', 'fraud', 'cover', 'amount', 'documents', 'customer'].map((filter) => `caseCockpit.attention.filters.${filter}`),
    ...['essential', 'detailed'].map((density) => `caseCockpit.attention.density.${density}`),
    ...['summary', 'fraud', 'web', 'cover', 'evidence', 'customer', 'timeline', 'data', 'pipeline']
      .map((tab) => `caseCockpit.drawer.tabs.${tab}`),
    ...['authentic', 'doubtful', 'suspicious'].map((badge) => `caseCockpit.evidence.badge.${badge}`),
    ...['calm', 'moderate', 'stressed', 'critical'].map((level) => `caseCockpit.kpi.customerLevels.${level}`),
    ...['LOW', 'MODERATE', 'HIGH'].map((band) => `caseCockpit.updates.bands.${band}`),
    ...['confirmed', 'notConfirmed', 'unclear', 'skipped'].flatMap((verdict) => [
      `caseCockpit.updates.kinds.web.${verdict}`,
      `caseCockpit.webTab.verdict.${verdict}`,
    ]),
    ...['ok', 'review', 'problem'].map((status) => `workbench.pipelineState.${status}`),
  ];

  // Every recommendation (and alternative) the rules can produce, as translation keys.
  const t = (key) => `nextAction.${key}`;
  const base = { analysisComplete: true, fraudRisk: 0.1, siuRecommended: false, inconsistentStatement: false, amount: 1200, amountLabel: '1,200' };
  const inputs = [
    { siuRecommended: true },
    { fraudRisk: 0.65 },
    { inconsistentStatement: true },
    { amount: 6560 },
    {},
    { fraudRisk: 0.4 },
  ];
  for (const input of inputs) {
    const result = recommendation.buildRecommendation({ ...base, ...input }, t);
    for (const option of [result, ...result.alternatives]) keys.push(option.title, option.reason);
  }

  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(path.join(messagesDir, `${locale}.json`), 'utf8'));
    const missing = keys.filter((key) => typeof lookup(messages, key) !== 'string');
    assert.deepEqual(missing, [], `${locale} is missing cockpit keys`);
  }
});
