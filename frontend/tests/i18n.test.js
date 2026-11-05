const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const { parse } = require('@formatjs/icu-messageformat-parser');

const root = path.resolve(__dirname, '..');

function messages(locale) {
  return JSON.parse(fs.readFileSync(path.join(root, 'messages', `${locale}.json`), 'utf8'));
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

test('English, French and German messages have exact key parity', () => {
  const expected = messageKeys(messages('en')).sort();
  assert.deepEqual(messageKeys(messages('fr')).sort(), expected);
  assert.deepEqual(messageKeys(messages('de')).sort(), expected);
});

test('localized messages have valid ICU syntax and matching arguments', () => {
  const source = new Map(messageValues(messages('en')));

  for (const locale of ['fr', 'de']) {
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
    auto: 'assets/demo-prevaiq/automotive-claims/parking-impact/',
    sante: 'assets/demo-prevaiq/health-underwriting/',
    'sante-sinistre': 'assets/demo-prevaiq/health-claims/dental/',
    hypothecaire: 'assets/demo-prevaiq/mortgage-underwriting/primo-accedant/app-mtg-004/',
  };

  for (const locale of ['en', 'fr', 'de']) {
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
  assert.match(requestConfig, /\['en', 'fr', 'de'\]/);
});

test('Ask IQ agent and workflow buttons preserve their API contracts', () => {
  const drawer = fs.readFileSync(
    path.join(root, 'src', 'components', 'ChatDrawer.tsx'),
    'utf8'
  );
  const api = fs.readFileSync(path.join(root, 'src', 'lib', 'api.ts'), 'utf8');

  for (const agent of ['auto', 'data', 'policy', 'analysis', 'dashboard', 'workflow']) {
    assert.match(drawer, new RegExp(`id: '${agent}'`), `missing ${agent} agent button`);
  }
  for (const workflow of ['express', 'complet', 'fraude']) {
    assert.match(drawer, new RegExp(`id: '${workflow}'`), `missing ${workflow} workflow button`);
  }

  assert.match(
    drawer,
    /\/api\/applications\/\$\{applicationId\}\/workflow\/\$\{workflowId\}/
  );
  assert.match(drawer, /body: JSON\.stringify\(\{ language: locale \}\)/);
  assert.match(drawer, /result\.status === 'needs_review'/);
  assert.match(drawer, /workflowNeedsReviewStatus/);
  assert.match(
    api,
    /\/api\/applications\/\$\{encodeURIComponent\(appId\)\}\/conversations/
  );
  assert.match(drawer, /agent_type: activeAgent/);
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

  for (const locale of ['en', 'fr', 'de']) {
    const localized = messages(locale).admin.processing[getApplicationLoadErrorKey(rawError)];
    assert.ok(localized.length < 110, `${locale} storage error should stay concise`);
    assert.doesNotMatch(localized, /AuthorizationFailure|<\?xml|RequestId/);
  }
});
