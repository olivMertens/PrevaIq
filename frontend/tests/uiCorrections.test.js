const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const ts = require('typescript');
const {createTranslator} = require('use-intl/core');
const {load, srcDir} = require('./loadTs');
const {localizeClaimSubject} = load('applicationDisplay.ts', path.join(srcDir, 'lib'));
const {buildGenericTimeline} = load('buildTimeline.ts', path.join(srcDir, 'components', 'chronology'));
const references = load('policyReferences.ts', path.join(srcDir, 'components', 'chat'));
const {APIError} = load('api.ts', path.join(srcDir, 'lib'));
const messagesFor = locale => JSON.parse(fs.readFileSync(
  path.join(srcDir, '..', 'messages', `${locale}.json`), 'utf8',
));
const settle = () => new Promise(resolve => setImmediate(resolve));

function moduleFrom(relative, overrides) {
  const filename = path.join(srcDir, ...relative.split('/'));
  const sourceModule = {exports: {}};
  const {outputText} = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    },
  });
  vm.runInThisContext(`(function(module,exports,require){${outputText}\n})`, {filename})(
    sourceModule, sourceModule.exports, name => name in overrides ? overrides[name] : require(name),
  );
  return sourceModule.exports;
}

for (const locale of ['en', 'fr', 'de']) {
  test(`${locale}: compound claim type and urgency use UI labels without rewriting evidence`, () => {
    const messages = messagesFor(locale);
    const subject = createTranslator({locale, messages, namespace: 'claimSubjects'});
    const timeline = createTranslator({locale, messages, namespace: 'chronological'});
    const source = 'tempête / dégât des eaux (sinistre élémentaire)';
    const app = {
      id: 'case', persona: 'habitation_claims', created_at: '2026-11-06T09:00:00Z',
      files: [], llm_outputs: {},
      extracted_fields: Object.fromEntries(Object.entries({
        NatureSinistre: source, NiveauUrgence: 'élevé', DateSinistre: '28/08/2026',
        DescriptionSinistre: 'Source evidence — keep verbatim',
      }).map(([key, value]) => [key, {field_name: key, value}])),
    };
    const original = JSON.stringify(app);
    const label = localizeClaimSubject(source, subject);
    assert.ok(label.includes(subject('storm')));
    assert.ok(label.includes(subject('water')));
    assert.ok(label.includes(subject('natural')));
    const entries = buildGenericTimeline(app, locale, timeline, 'CHF', subject);
    assert.ok(entries.some(entry => entry.title.includes(label)));
    assert.ok(entries.some(entry => entry.title.includes(subject('high'))));
    assert.ok(entries.some(entry => entry.details === 'Source evidence — keep verbatim'));
    assert.equal(JSON.stringify(app), original);
    if (locale !== 'fr') {
      assert.ok(!entries.some(entry => /élevé|tempête|dégât des eaux/.test(entry.title)));
    }
  });
}

test('urgency flags are recognized consistently from French, English and German enum values', () => {
  const messages = messagesFor('en');
  const t = createTranslator({locale: 'en', messages, namespace: 'chronological'});
  const subject = createTranslator({locale: 'en', messages, namespace: 'claimSubjects'});
  for (const value of ['élevé', 'High', 'Hoch', 'Critique', 'Critical', 'Kritisch']) {
    const entries = buildGenericTimeline({
      persona: 'habitation_claims', created_at: '2026-11-06T09:00:00Z', files: [],
      extracted_fields: {NiveauUrgence: {value}},
    }, 'en', t, 'CHF', subject);
    assert.ok(entries.some(entry => entry.title.includes('Urgency level')));
  }
});

test('successful Aurora refresh clears only the resolved saved-load error', async () => {
  async function check(statusFailure) {
    let state;
    const effects = [];
    const hook = moduleFrom('components/case/useAuroraEvidence.ts', {
      react: {
        useState: initial => {
          if (state === undefined) state = initial;
          return [state, update => { state = typeof update === 'function' ? update(state) : update; }];
        },
        useEffect: effect => effects.push(effect),
        useCallback: callback => callback,
      },
      '@/lib/api': {
        APIError,
        getAuroraStatus: () => statusFailure ? Promise.reject(new Error('offline'))
          : Promise.resolve({enabled: true, mode: 'demo_simulation'}),
        getAuroraForecast: () => Promise.reject(new APIError(500, 'saved read failed')),
      },
    });
    hook.useAuroraEvidence('case');
    effects[0]();
    await settle();
    assert.equal(state.error, statusFailure ? 'statusError' : 'loadError');
    const saved = {provenance: {source: 'demo_simulation'}, forecast: {series: []}};
    hook.useAuroraEvidence('case').setForecast(saved, {kind: 'demo_simulation'});
    assert.equal(state.forecast, saved);
    assert.equal(state.error, statusFailure ? 'statusError' : null);
  }
  await check(false);
  await check(true);
});

const citations = [
  {policy_id: 'PC-001', policy_name: 'Policy one', chunk_type: 'condition', criteria_id: 'PC-001-C1'},
  {policy_id: 'PC-002', policy_name: 'Policy two', chunk_type: 'condition', criteria_id: 'shared-rule'},
  {policy_id: 'PC-001', policy_name: 'Policy one', chunk_type: 'condition', criteria_id: 'shared-rule'},
];

test('policy references link only verified unambiguous ids, not code, existing links or guesses', () => {
  const tree = {type: 'root', children: [
    {type: 'paragraph', children: [{type: 'text', value: 'PC-001 and PC-001-C1, not PC-0010 or PC-999 or shared-rule.'}]},
    {type: 'code', value: 'PC-001'},
    {type: 'paragraph', children: [
      {type: 'inlineCode', value: 'PC-001'},
      {type: 'link', url: 'https://example.com', children: [{type: 'text', value: 'PC-001'}]},
    ]},
  ]};
  references.policyReferencePlugin(citations)()(tree);
  const linked = tree.children[0].children.filter(node => node.type === 'link');
  assert.equal(linked.length, 2);
  assert.ok(linked.every(node => node.url === '#policy/PC-001'));
  assert.equal(tree.children[1].value, 'PC-001');
  assert.equal(tree.children[2].children[0].type, 'inlineCode');
  assert.equal(tree.children[2].children[1].url, 'https://example.com');
  assert.ok(!references.citationReferenceMap(citations).has('shared-rule'));
});

test('answers render safe bold, italic and underlined clickable policy references', async () => {
  const ReactMarkdown = (await import('react-markdown')).default;
  const remarkGfm = (await import('remark-gfm')).default;
  const messages = messagesFor('en');
  const opened = [];
  const component = moduleFrom('components/chat/ChatMarkdown.tsx', {
    react: {...React, useMemo: fn => fn()},
    'react-markdown': {__esModule: true, default: ReactMarkdown},
    'remark-gfm': {__esModule: true, default: remarkGfm},
    './policyReferences': references,
    'next-intl': {useTranslations: namespace => createTranslator({locale: 'en', messages, namespace})},
  }).default;
  const props = {
    content: '## Review\n**Important** and *indicative*. See PC-001 and PC-999.\n\n`PC-001`\n\n[unsafe](javascript:alert)\n<script>alert(1)</script>',
    citations, onPolicyClick: id => opened.push(id),
  };
  const html = renderToStaticMarkup(React.createElement(component, props));
  assert.match(html, /<strong[^>]*>Important<\/strong>/);
  assert.match(html, /<em[^>]*>indicative<\/em>/);
  assert.match(html, /<button[^>]*underline[^>]*>PC-001<\/button>/);
  assert.doesNotMatch(html, /href="javascript:|<script/);
  assert.match(html, /<code[^>]*>PC-001<\/code>/);
  const markdown = component(props).props.children;
  const policyLink = markdown.props.components.a({href: '#policy/PC-001', children: 'PC-001'});
  policyLink.props.onClick();
  assert.deepEqual(opened, ['PC-001']);
  const unknown = markdown.props.components.a({href: '#policy/PC-999', children: 'PC-999'});
  assert.equal(unknown.type, 'span');
});

test('currency admin control exposes named choices and a no-conversion hint while login stays native', () => {
  const messages = messagesFor('en');
  const changes = [];
  const component = moduleFrom('components/CurrencySwitcher.tsx', {
    react: {...React, useState: () => [true, () => {}], useId: () => 'currency-menu',
      useEffect: () => {}, useRef: () => ({current: null})},
    'next-intl': {useTranslations: namespace => createTranslator({locale: 'en', messages, namespace})},
    '@/lib/currency': load('currency.ts', path.join(srcDir, 'lib')),
    '@/lib/CurrencyProvider': {useReferenceCurrency: () => ({currency: 'CHF', setCurrency: next => changes.push(next)})},
    './auth/login.module.css': {},
  });
  const html = renderToStaticMarkup(React.createElement(component.default));
  assert.match(html, /aria-haspopup="menu"/);
  assert.match(html, /role="menuitemradio"/);
  assert.ok(html.includes('Swiss franc'));
  assert.ok(html.includes(messages.currency.referenceHint));
  assert.doesNotMatch(html, /<select/);
  const login = renderToStaticMarkup(React.createElement(component.default, {variant: 'login'}));
  assert.match(login, /<select/);
  const options = component.CurrencyOptions();
  options.props.children[0][0].props.onClick();
  assert.deepEqual(changes, ['USD']);
});

test('proposal chips have no nested scroll strip and retain the complete accessible label', () => {
  const component = moduleFrom('components/chat/ChatSuggestions.tsx', {}).default;
  const suggestion = 'A long suggested insurance question that should stay readable without a scrollbar';
  const selected = [];
  const element = component({suggestions: [suggestion], compact: true, onSelect: value => selected.push(value)});
  const html = renderToStaticMarkup(element);
  assert.doesNotMatch(html, /overflow-x-auto|overflow-y-auto|whitespace-nowrap/);
  assert.ok(html.includes(`title="${suggestion}"`));
  element.props.children[0].props.onClick();
  assert.deepEqual(selected, [suggestion]);
});
