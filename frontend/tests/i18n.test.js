const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const { parse } = require('@formatjs/icu-messageformat-parser');
const { load, srcDir } = require('./loadTs');

const root = path.resolve(__dirname, '..');
const { swissGermanMessages, sameLanguage } = load('locales.ts', path.join(srcDir, 'i18n'));
const locales = ['en', 'fr', 'de', 'de-CH'];

function messages(locale) {
  const catalog = JSON.parse(fs.readFileSync(
    path.join(root, 'messages', `${locale === 'de-CH' ? 'de' : locale}.json`), 'utf8'
  ));
  return locale === 'de-CH' ? swissGermanMessages(catalog) : catalog;
}

function messageKeys(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const qualified = prefix ? `${prefix}.${key}` : key;
    return child && typeof child === 'object'
      ? messageKeys(child, qualified)
      : [qualified];
  });
}

function messageValues(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const qualified = prefix ? `${prefix}.${key}` : key;
    return child && typeof child === 'object'
      ? messageValues(child, qualified)
      : [[qualified, child]];
  });
}

function messageArguments(message) {
  const names = new Set();
  const visit = (elements) => {
    for (const element of elements) {
      if (element.type >= 1 && element.type <= 6) {
        names.add(element.value);
      }
      if (element.options) {
        Object.values(element.options).forEach((option) => visit(option.value));
      }
      if (element.children) {
        visit(element.children);
      }
    }
  };
  visit(parse(message));
  return [...names].sort();
}

test('German locale exposes the core navigation and authentication labels', () => {
  const de = messages('de');
  assert.equal(de.auth.languageGerman, 'Deutsch');
  assert.equal(de.nav.overview, 'Übersicht');
  assert.equal(de.status.processing, 'In Bearbeitung');
});

test('English, French, German and Swiss German messages have exact key parity', () => {
  const expected = messageKeys(messages('en')).sort();
  for (const locale of locales) assert.deepEqual(messageKeys(messages(locale)).sort(), expected);
});

test('Swiss German inherits German messages without eszett, including nested demo steps', () => {
  const german = messages('de');
  const swiss = messages('de-CH');
  assert.equal(swiss.auth.languageGermanSwiss, 'Deutsch (Schweiz)');
  assert.equal(swiss.demoGuide.close, 'Schliessen');
  assert.equal(german.demoGuide.close, 'Schließen');
  assert.doesNotMatch(JSON.stringify(swiss), /[ßẞ]/);
  assert.match(JSON.stringify(german), /ß/);
  assert.deepEqual(
    swissGermanMessages({ Straße: 'GRẞ / Straße {count}', steps: [{ text: 'Schließen' }], count: 2, empty: null }),
    { Straße: 'GRSS / Strasse {count}', steps: [{ text: 'Schliessen' }], count: 2, empty: null }
  );
  assert.match(swiss.demoGuide.scenarios['habitation-ch'].steps[4].detail, /DE-CH/);
});

test('the request config restores the regional cookie and preserves existing locale defaults', async () => {
  const filename = path.join(root, 'src', 'i18n', 'request.ts');
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  for (const cookie of [...locales, undefined, 'invalid']) {
    const sourceModule = { exports: {} };
    const requireSource = (specifier) => {
      if (specifier === 'next-intl/server') return { getRequestConfig: (config) => config };
      if (specifier === 'next/headers') return { cookies: async () => ({ get: () => cookie ? { value: cookie } : undefined }) };
      if (specifier === './locales') return { swissGermanMessages };
      if (specifier.startsWith('../../messages/')) {
        return { default: JSON.parse(fs.readFileSync(path.resolve(path.dirname(filename), specifier), 'utf8')) };
      }
      throw new Error(`Unexpected request-config import: ${specifier}`);
    };
    vm.runInThisContext(`(function(module, exports, require) {${outputText}\n})`)(
      sourceModule, sourceModule.exports, requireSource
    );
    const config = await sourceModule.exports.default();
    const expected = locales.includes(cookie) ? cookie : 'en';
    assert.equal(config.locale, expected);
    assert.deepEqual(config.messages, messages(expected));
  }
});

test('Swiss German uses regional number formats without retranslating German source evidence', () => {
  assert.equal(sameLanguage('de', 'de-CH'), true);
  assert.equal(sameLanguage('de-CH', 'DE'), true);
  assert.equal(sameLanguage('en', 'de-CH'), false);
  assert.equal(sameLanguage('fr', 'de-CH'), false);
  assert.match(new Intl.NumberFormat('de-CH').format(12345.67), /^12['’]345\.67$/);
});

test('every Swiss German label renders with its ICU arguments and without translation errors', () => {
  const { createTranslator } = require('use-intl/core');
  const errors = [];
  let currentKey = '';
  const translate = createTranslator({
    locale: 'de-CH',
    messages: messages('de-CH'),
    onError: (error) => errors.push(`${currentKey}: ${error.code}`),
  });
  function argumentsFor(elements, values = {}) {
    for (const element of elements) {
      if (element.type === 1) values[element.value] ??= 'Beispiel';
      if (element.type === 2 || element.type === 6) values[element.value] = 2;
      if (element.type === 3 || element.type === 4) values[element.value] = new Date('2026-11-06T12:00:00Z');
      if (element.type === 5) values[element.value] = 'other';
      if (element.type === 8) values[element.value] = (chunks) => chunks;
      for (const option of Object.values(element.options || {})) argumentsFor(option.value, values);
      if (element.children) argumentsFor(element.children, values);
    }
    return values;
  }
  const labels = messageValues(messages('de-CH'));
  for (const [key, message] of labels) {
    currentKey = key;
    const rendered = translate.rich(key, argumentsFor(parse(message)));
    if (typeof rendered === 'string') assert.doesNotMatch(rendered, /[ßẞ]/, key);
  }
  assert.deepEqual(errors, []);
  assert.ok(labels.length > 3000, 'the complete catalog must be exercised');
});

test('Swiss German fallback case titles stay German without rewriting source labels', () => {
  const { getApplicationDisplayTitle } = load('applicationDisplay.ts', path.join(srcDir, 'lib'));
  for (const [persona, prefix] of [
    ['automotive_claims', 'Kfz-Schaden'],
    ['habitation_claims', 'Sachschaden'],
    ['life_health_claims', 'Gesundheitsschaden'],
    ['underwriting', 'Schadenfall'],
  ]) {
    const app = { id: 'DECH-TEST', persona, files: [{ filename: 'photo-dommage.pdf' }] };
    assert.equal(getApplicationDisplayTitle(app, 'de-CH'), `${prefix} — dommage`, persona);
    assert.equal(getApplicationDisplayTitle(app, 'de-CH'), getApplicationDisplayTitle(app, 'de'));
    assert.equal(
      getApplicationDisplayTitle({ ...app, summary_title: 'Firma Straße AG — POL-CH-123' }, 'de-CH'),
      'Firma Straße AG — POL-CH-123'
    );
  }
});

test('Swiss German API features preserve the requested variant, options and review decisions', async (t) => {
  const api = load('api.ts', path.join(srcDir, 'lib'));
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    requests.push({ url: new URL(url, 'http://localhost'), method: options.method || 'GET', body: options.body && JSON.parse(options.body) });
    return Response.json({ id: 'swiss-demo', processing_status: 'completed' });
  });
  const appId = 'swiss-demo';
  const locale = 'de-CH';
  for (const [run, expectedLanguage, method] of [
    [() => api.getApplication(appId, locale), locale, 'GET'],
    [() => api.startProcessing(appId, 'standard', locale), locale, 'POST'],
    [() => api.runRiskAnalysis(appId, 1000, 1, locale), locale, 'POST'],
    [() => api.runUnderwritingAnalysis(appId, ['summary'], true, locale), locale, 'POST'],
    [() => api.getPropertyDeepDive(appId, locale), locale, 'GET'],
    [() => api.runPropertyDeepDive(appId, true, locale), locale, 'POST'],
    [() => api.getFraudAnalysis(appId, locale), locale, 'GET'],
    [() => api.runFraudAnalysis(appId, 'image.jpg', 'high', locale), locale, 'POST'],
    [() => api.getGlossary('habitation_claims', locale), locale, 'GET'],
    [() => api.translateApplicationContent(appId, { language: locale, pages: [12], batches: [2] }), locale, 'POST'],
    [() => api.sendConversation(appId, {
      message: 'Welche Deckung gilt?', conversation_id: null, persona: 'habitation_claims',
      agent_type: 'policy', use_corrections: true, language: locale,
    }, new AbortController().signal), locale, 'POST'],
  ]) {
    const before = requests.length;
    await run();
    const sent = requests.slice(before);
    assert.ok(sent.length > 0);
    assert.equal(sent[0].method, method);
    for (const request of sent) {
      assert.equal(request.body?.language || request.url.searchParams.get('language'), expectedLanguage, request.url.pathname);
    }
  }
  assert.equal(requests.find(({ url }) => url.pathname.endsWith('/process')).url.searchParams.get('processing_mode'), 'standard');
  assert.deepEqual(requests.find(({ url }) => url.pathname.endsWith('/analyze')).body.sections, ['summary']);
  const fraud = requests.find(({ url, method }) => url.pathname.endsWith('/fraud-analysis') && method === 'POST');
  assert.equal(fraud.url.searchParams.get('filename'), 'image.jpg');
  assert.equal(fraud.url.searchParams.get('reasoning_effort'), 'high');
  assert.deepEqual(requests.find(({ url }) => url.pathname.endsWith('/content-translations')).body.pages, [12]);
  const decision = { decision: 'approve_with_conditions', notes: 'Belege geprüft', conditions: 'Gutachten erforderlich' };
  await api.submitApplicationDecision(appId, decision);
  assert.equal(requests.at(-1).method, 'PUT');
  assert.deepEqual(requests.at(-1).body, decision);
});

test('case loading also preserves DE-CH when the locale comes from the current HTML document', async (t) => {
  const api = load('api.ts', path.join(srcDir, 'lib'));
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { documentElement: { lang: 'de-CH' } } });
  t.after(() => {
    if (descriptor) Object.defineProperty(globalThis, 'document', descriptor);
    else delete globalThis.document;
  });
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url) => {
    requests.push(url);
    return Response.json({ id: 'swiss-demo' });
  });
  await api.getApplication('swiss-demo');
  assert.equal(new URL(requests[0], 'http://localhost').searchParams.get('language'), 'de-CH');
});

test('persona menu names are translated rather than copied from the French registry', () => {
  const expected = {
    en: ['Life & Health Underwriting', 'Mortgage Underwriting', 'Health Claims', 'Auto Claims', 'Property Claims'],
    fr: ['Souscription Vie & Santé', 'Souscription Hypothécaire', 'Sinistres Santé', 'Sinistres Auto', 'Sinistres Habitation'],
    de: ['Risikoprüfung Leben & Gesundheit', 'Hypothekenprüfung', 'Gesundheitsschäden', 'Kfz-Schäden', 'Sachschäden'],
    'de-CH': ['Risikoprüfung Leben & Gesundheit', 'Hypothekenprüfung', 'Gesundheitsschäden', 'Kfz-Schäden', 'Sachschäden'],
  };
  const ids = ['underwriting', 'mortgage', 'life_health_claims', 'automotive_claims', 'habitation_claims'];
  for (const locale of locales) {
    const labels = messages(locale).persona.labels;
    assert.deepEqual(ids.map((id) => labels[id]), expected[locale]);
    assert.ok(labels.property_casualty_claims);
    assert.ok(labels.securities_lending);
  }
  const selector = fs.readFileSync(path.join(root, 'src', 'components', 'PersonaSelector.tsx'), 'utf8');
  const provider = fs.readFileSync(path.join(root, 'src', 'lib', 'PersonaContext.tsx'), 'utf8');
  assert.match(selector, /t\(`labels\.\$\{currentPersona\}`\)/);
  assert.match(selector, /t\(`labels\.\$\{persona\.id\}`\)/);
  assert.doesNotMatch(selector, /catch\s*\{|return fallback/);
  assert.match(provider, /useTranslations\('persona\.labels'\)/);
  assert.match(provider, /name: t\(currentPersona\)/);
});

test('demo tabs and selection instructions match the translated persona menu', () => {
  const scenarios = {
    habitation: 'habitation_claims',
    'habitation-ch': 'habitation_claims',
    'habitation-ch-watch': 'habitation_claims',
    auto: 'automotive_claims',
    sante: 'underwriting',
    'sante-sinistre': 'life_health_claims',
    hypothecaire: 'mortgage',
  };
  for (const locale of locales) {
    const content = messages(locale);
    for (const [scenario, persona] of Object.entries(scenarios)) {
      const label = content.persona.labels[persona];
      const demo = content.demoGuide.scenarios[scenario];
      assert.ok(demo.label.startsWith(label), `${locale}.${scenario} tab must match the menu`);
      assert.ok(demo.steps[0].title.includes(label), `${locale}.${scenario} instruction must match the menu`);
    }
  }
});

test('localized messages have valid ICU syntax and matching arguments', () => {
  const source = new Map(messageValues(messages('en')));

  for (const locale of ['fr', 'de', 'de-CH']) {
    for (const [key, localized] of messageValues(messages(locale))) {
      assert.doesNotMatch(localized, /ZXQPH|QXZ/, `${locale}.${key} contains a translation token`);
      assert.deepEqual(
        messageArguments(localized),
        messageArguments(source.get(key)),
        `${locale}.${key} must preserve the English ICU arguments`
      );
    }
  }
});

test('demo guide content is next-intl backed for all locales', () => {
  const demoPaths = {
    habitation: 'assets/demo-prevaiq/property-claims/wine-cellar/',
    'habitation-ch': 'assets/demo-prevaiq/property-claims/swiss-chocolate-storm/',
    'habitation-ch-watch': 'assets/demo-prevaiq/property-claims/swiss-watch-storm/',
    auto: 'assets/demo-prevaiq/automotive-claims/parking-impact/',
    sante: 'assets/demo-prevaiq/health-underwriting/',
    'sante-sinistre': 'assets/demo-prevaiq/health-claims/dental/',
    hypothecaire: 'assets/demo-prevaiq/mortgage-underwriting/primo-accedant/app-mtg-004/',
  };

  for (const locale of locales) {
    const guide = messages(locale).demoGuide;
    assert.ok(guide.title);
    assert.ok(guide.scenarios.habitation.steps.length > 0);
    assert.ok(guide.scenarios.client360.summary);
    for (const [scenario, demoPath] of Object.entries(demoPaths)) {
      const tips = guide.scenarios[scenario].steps
        .map((step) => step.tip || '')
        .join('\n');
      assert.match(tips, new RegExp(demoPath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
      assert.ok(fs.existsSync(path.resolve(root, '..', demoPath)), demoPath);
    }
  }

  const modal = fs.readFileSync(
    path.join(root, 'src', 'components', 'DemoGuideModal.tsx'),
    'utf8'
  );
  assert.doesNotMatch(modal, /isFr|titleEn|detailEn|summaryEn/);
  assert.match(modal, /useTranslations\('demoGuide'\)/);
});

test('all locale selectors and agent languages include German', () => {
  const switcher = fs.readFileSync(
    path.join(root, 'src', 'components', 'LanguageSwitcher.tsx'),
    'utf8'
  );
  const requestConfig = fs.readFileSync(path.join(root, 'src', 'i18n', 'request.ts'), 'utf8');

  assert.match(switcher, /code: 'de'/);
  assert.match(switcher, /code: 'de-CH'.*flag: '🇨🇭'/);
  assert.match(requestConfig, /\['en', 'fr', 'de', 'de-CH'\]/);
});

test('Ask IQ agent and workflow buttons preserve their API contracts', () => {
  const read = (...parts) => fs.readFileSync(path.join(root, 'src', 'components', ...parts), 'utf8');
  const drawer = read('ChatDrawer.tsx');
  const modeBar = read('chat', 'ChatModeBar.tsx');
  const picker = read('chat', 'WorkflowPicker.tsx');
  const workflowResult = read('chat', 'WorkflowResult.tsx');
  const workflowRequest = read('chat', 'useWorkflowRequest.ts');
  const api = fs.readFileSync(path.join(root, 'src', 'lib', 'api.ts'), 'utf8');

  for (const agent of ['auto', 'data', 'policy', 'analysis', 'dashboard', 'workflow']) {
    assert.match(modeBar, new RegExp(`id: '${agent}'`), `missing ${agent} agent button`);
  }
  for (const workflow of ['express', 'complet', 'fraude']) {
    assert.match(picker, new RegExp(`id: '${workflow}'`), `missing ${workflow} workflow button`);
  }

  assert.match(
    workflowRequest,
    /\/api\/applications\/\$\{encodeURIComponent\(applicationId\)\}\/workflow\/\$\{encodeURIComponent\(workflowId\)\}/
  );
  assert.match(drawer, /runWorkflowRequest\(workflowId, locale/);
  assert.match(drawer, /if \(!inputValue\.trim\(\) \|\| isLoading \|\| workflowRunning\) return/);
  assert.match(workflowRequest, /body: JSON\.stringify\(\{ language, stream: true \}\)/);
  assert.match(drawer, /result\.status === 'needs_review'/);
  assert.match(workflowResult, /workflowNeedsReviewStatus/);
  assert.match(
    api,
    /\/api\/applications\/\$\{encodeURIComponent\(appId\)\}\/conversations/
  );
  // Typed questions never reach the workflow mode, nor Fabric when it is not configured.
  assert.match(drawer, /activeAgent === 'workflow' \|\| \(activeAgent === 'data' && !capabilities\.fabric_data\)/);
  assert.match(drawer, /agent_type: agentType/);
  assert.match(drawer, /language: locale/);
});

test('admin errors and account identities are compacted by executable UI helpers', () => {
  const filename = path.join(root, 'src', 'lib', 'displayText.ts');
  const sourceModule = { exports: {} };
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  vm.runInNewContext(outputText, { module: sourceModule, exports: sourceModule.exports }, { filename });
  const { compactAuthIdentity, getApplicationLoadErrorKey } = sourceModule.exports;

  const rawError = new Error(
    'AuthorizationFailure <?xml version="1.0"?><Error>This request is not authorized to perform this operation.</Error>'
  );
  assert.equal(getApplicationLoadErrorKey(rawError), 'storageUnavailable');
  assert.equal(getApplicationLoadErrorKey(new Error('HTTP 500')), 'loadApplicationsFailed');
  assert.equal(compactAuthIdentity('prevaiq-admin@example.test'), 'prevaiq-admin');
  assert.equal(compactAuthIdentity(null), null);

  for (const locale of locales) {
    const localized = messages(locale).admin.processing[getApplicationLoadErrorKey(rawError)];
    assert.ok(localized.length < 110, `${locale} storage error should stay concise`);
    assert.doesNotMatch(localized, /AuthorizationFailure|<\?xml|RequestId/);
  }
});
