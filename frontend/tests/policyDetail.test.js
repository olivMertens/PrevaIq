const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {createTranslator} = require('use-intl/core');
const ts = require('typescript');

const root = path.resolve(__dirname, '..', '..');
const policy = JSON.parse(fs.readFileSync(
  path.join(root, 'prompts', 'property-casualty-claims-policies.json'), 'utf8',
)).policies[0];
const settle = () => new Promise(resolve => setImmediate(resolve));
const response = (data, status = 200) => ({ok: status === 200, status, json: async () => data});

function harness(fetch, locale = 'en') {
  const states = [];
  const effects = [];
  const warnings = [];
  let stateIndex;
  let effectIndex;
  const messages = JSON.parse(fs.readFileSync(
    path.join(root, 'frontend', 'messages', `${locale}.json`), 'utf8',
  ));
  const t = createTranslator({locale, messages, namespace: 'policyDetail'});
  const hooks = {
    ...React,
    useState(initial) {
      const i = stateIndex++;
      if (!(i in states)) states[i] = initial;
      return [states[i], update => {
        states[i] = typeof update === 'function' ? update(states[i]) : update;
      }];
    },
    useEffect(callback, dependencies) {
      const i = effectIndex++;
      const prior = effects[i];
      if (!prior || dependencies.some((value, j) => value !== prior.dependencies[j])) {
        prior?.cleanup?.();
        effects[i] = {callback, dependencies, pending: true};
      }
    },
  };
  const filename = path.join(root, 'frontend', 'src', 'components', 'chat', 'PolicyDetailModal.tsx');
  const {outputText} = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    },
  });
  const mod = {exports: {}};
  vm.runInThisContext(
    `(function(module,exports,require,fetch,console,document){${outputText}\n})`, {filename},
  )(mod, mod.exports, name => name === 'react' ? hooks
    : name === 'next-intl' ? {useTranslations: () => t} : require(name),
  fetch, {warn: (...args) => warnings.push(args)}, {addEventListener() {}, removeEventListener() {}});
  const onClose = () => {};
  return {
    states, warnings, t, validate: mod.exports.isPolicyDetail,
    render(id = policy.id, persona = 'habitation_claims') {
      stateIndex = 0;
      effectIndex = 0;
      const element = mod.exports.default({policyId: id, persona, onClose});
      for (const effect of effects) {
        if (effect.pending) {
          effect.pending = false;
          effect.cleanup = effect.callback();
        }
      }
      return element;
    },
  };
}

function retryButton(element, label) {
  if (!React.isValidElement(element)) return null;
  if (element.type === 'button' && element.props.children === label) return element;
  for (const child of React.Children.toArray(element.props.children)) {
    const found = retryButton(child, label);
    if (found) return found;
  }
  return null;
}

test('viewer validates real criteria without a risk level and rejects wrong or malformed policies', () => {
  const h = harness(() => {});
  assert.equal(h.validate(policy, policy.id), true);
  assert.equal(h.validate({policy}, policy.id), false);
  assert.equal(h.validate({...policy, id: 'PC-OTHER'}, policy.id), false);
  assert.equal(h.validate({...policy, criteria: [{}]}, policy.id), false);
  assert.equal(h.validate({...policy, references: [null]}, policy.id), false);
});

for (const locale of ['en', 'fr', 'de']) {
  test(`${locale}: transport failure is localized, logged and recoverable with Retry`, async () => {
    const requests = [];
    const h = harness((url, options) => {
      requests.push({url, signal: options.signal});
      return requests.length === 1 ? Promise.reject(new TypeError('Failed to fetch'))
        : Promise.resolve(response({policy}));
    }, locale);
    h.render();
    await settle();
    assert.equal(h.states[2], h.t('loadError'));
    assert.equal(h.warnings.length, 1);
    const failed = h.render();
    assert.doesNotMatch(renderToStaticMarkup(failed), /Failed to fetch/);
    retryButton(failed, h.t('retry')).props.onClick();
    h.render();
    await settle();
    assert.equal(requests[0].signal.aborted, true);
    assert.equal(requests[1].url, `/api/policies/${policy.id}?persona=habitation_claims`);
    assert.equal(h.states[0], policy);
    assert.equal(h.states[2], null);
    const html = renderToStaticMarkup(h.render());
    assert.match(html, /Property Damage Coverage Verification/);
    assert.match(html, /C1/);
    assert.doesNotMatch(html, /Failed to fetch/);
  });
}

test('HTTP failures retain diagnostics and invalid successful bodies never populate the viewer', async () => {
  for (const [data, status, key] of [
    [null, 404, 'requestError'],
    ['sign-in HTML', 200, 'invalidResponse'],
    [{...policy, id: 'PC-WRONG'}, 200, 'invalidResponse'],
  ]) {
    const h = harness(async () => response(data, status));
    h.render();
    await settle();
    assert.equal(h.states[0], null);
    assert.equal(h.states[2], h.t(key, {status}));
    assert.equal(h.states[1], false);
  }
});

test('changing policy or persona cancels the prior request and isolates a late response', async () => {
  const requests = [];
  const h = harness((url, options) => new Promise(resolve => {
    requests.push({url, signal: options.signal, resolve});
  }));
  h.render();
  const other = {...policy, id: 'PC-OTHER'};
  h.render(other.id, 'automotive_claims');
  assert.equal(requests[0].signal.aborted, true);
  requests[1].resolve(response(other));
  await settle();
  assert.equal(h.states[0], other);
  requests[0].resolve(response(policy));
  await settle();
  assert.equal(h.states[0], other);
  assert.equal(h.states[2], null);
  assert.equal(h.warnings.length, 0);
});
