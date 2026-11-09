const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {createTranslator} = require('use-intl/core');
const {NextRequest} = require('next/server');
const {load, srcDir} = require('./loadTs');
const api = load('api.ts', path.join(srcDir, 'lib'));
const originalFetch = global.fetch;

function summary(id, app = 'case-a') {
  return {
    id, application_id: app, persona: null, preview: null, title: `Title ${id}`,
    created_at: '2026-11-09T08:00:00Z', updated_at: '2026-11-09T08:00:00Z', message_count: 2,
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
function mockFetch(t, fetcher) {
  global.fetch = fetcher;
  t.after(() => { global.fetch = originalFetch; });
}

function mountHistory(t, {applicationId = 'case-a', locale = 'en', collapsed = false} = {}) {
  const filename = path.join(srcDir, 'components', 'chat', 'ChatHistoryPanel.tsx');
  const messages = JSON.parse(fs.readFileSync(
    path.join(srcDir, '..', 'messages', `${locale}.json`), 'utf8',
  ));
  const translator = createTranslator({locale, messages, namespace: 'chatHistory'});
  const slots = [];
  const effects = [];
  const warnings = [];
  const errors = [];
  const selections = [];
  const browser = {};
  let cursor = 0;
  let queued = false;
  let mounted = true;
  let tree;
  const props = {
    applicationId, currentConversationId: null, isCollapsed: collapsed,
    onSelectConversation: (...args) => selections.push(args),
    onNewConversation() {}, onToggleCollapse() {},
  };
  const equal = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const enqueue = () => {
    if (!queued && mounted) {
      queued = true;
      queueMicrotask(() => { queued = false; if (mounted) render(); });
    }
  };
  const hooks = {
    ...React,
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => {
        slots[index] = typeof value === 'function' ? value(slots[index]) : value;
        enqueue();
      }];
    },
    useRef(initial) {
      const index = cursor++;
      return slots[index] || (slots[index] = {current: initial});
    },
    useCallback(callback, deps) {
      const index = cursor++;
      if (!slots[index] || !equal(slots[index].deps, deps)) slots[index] = {deps, callback};
      return slots[index].callback;
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!slots[index] || !equal(slots[index].deps, deps)) {
        const old = slots[index];
        slots[index] = {deps, cleanup: old?.cleanup};
        effects.push(() => {
          old?.cleanup?.();
          slots[index].cleanup = effect();
        });
      }
    },
  };
  const sourceModule = {exports: {}};
  const {outputText} = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2020, esModuleInterop: true,
    },
  });
  const localRequire = name => {
    if (name === 'react') return hooks;
    if (name === 'next-intl') return {useLocale: () => locale, useTranslations: () => translator};
    if (name === '@/lib/api') return api;
    return require(name);
  };
  vm.runInThisContext(`(function(module,exports,require,window,console){${outputText}\n})`)(
    sourceModule, sourceModule.exports, localRequire, browser,
    {warn: (...args) => warnings.push(args), error: (...args) => errors.push(args)},
  );
  function render() {
    cursor = 0;
    tree = sourceModule.exports.default(props);
    for (const effect of effects.splice(0)) effect();
  }
  function buttons(node) {
    if (Array.isArray(node)) return node.flatMap(child => buttons(child));
    if (!React.isValidElement(node)) return [];
    return [...(node.type === 'button' ? [node] : []), ...buttons(node.props.children)];
  }
  render();
  t.after(() => {
    mounted = false;
    for (const slot of slots) slot?.cleanup?.();
  });
  return {
    html: () => renderToStaticMarkup(tree),
    button: label => {
      const button = buttons(tree).find(node => node.props['aria-label'] === label || node.props.title === label);
      assert.ok(button, `Button not found: ${label}`);
      return button;
    },
    update: value => { Object.assign(props, value); render(); },
    browser, warnings, errors, selections, messages,
  };
}

test('history client preserves 404/500 status and never returns a synthetic empty list', async t => {
  for (const status of [401, 403, 404, 500, 503]) {
    mockFetch(t, async () => Response.json({detail: 'unavailable'}, {status}));
    await assert.rejects(api.listConversations('case-a', new AbortController().signal),
      error => error instanceof api.APIError && error.status === status);
  }
});

test('history client validates payloads, accepts real empty history and encodes case ids', async t => {
  for (const payload of [{}, {conversations: null}, {conversations: {}}, {conversations: [{id: 'bad'}]}]) {
    mockFetch(t, async () => Response.json(payload));
    await assert.rejects(api.listConversations('case-a', new AbortController().signal),
      error => error.code === 'invalid_conversation_history');
  }
  const controller = new AbortController();
  mockFetch(t, async (url, options) => {
    assert.equal(url, '/api/applications/reference%2Fwith%20space/conversations');
    assert.equal(options.signal, controller.signal);
    assert.equal(options.cache, 'no-store');
    return Response.json({conversations: []});
  });
  assert.deepEqual(await api.listConversations('reference/with space', controller.signal), []);
});

test('a failed history load shows HTTP diagnostics and Retry without a console-error overlay', async t => {
  let count = 0;
  mockFetch(t, async () => ++count === 1
    ? Response.json({detail: 'route missing'}, {status: 404})
    : Response.json({conversations: [summary('recovered')]}));
  const history = mountHistory(t);
  await settle();
  assert.match(history.html(), /role="alert"/);
  assert.match(history.html(), /HTTP 404/);
  assert.doesNotMatch(history.html(), /No conversations yet/);
  assert.equal(history.errors.length, 0);
  assert.equal(history.warnings[0][1].status, 404);
  history.button('Retry').props.onClick();
  await settle();
  assert.match(history.html(), /Title recovered/);
  assert.doesNotMatch(history.html(), /role="alert"/);
  let buttonDepth = 0;
  for (const tag of history.html().match(/<\/?button\b[^>]*>/g) || []) {
    buttonDepth += tag.startsWith('</') ? -1 : 1;
    assert.ok(buttonDepth >= 0 && buttonDepth <= 1, 'History buttons must not be nested');
  }
  assert.equal(buttonDepth, 0);
});

test('late responses cannot replace another case history and requests are cancelled', async t => {
  let resolveFirst;
  let firstSignal;
  mockFetch(t, (url, options) => {
    if (url.includes('case-a')) {
      firstSignal = options.signal;
      return new Promise(resolve => { resolveFirst = resolve; });
    }
    return Promise.resolve(Response.json({conversations: [summary('correct-case', 'case-b')]}));
  });
  const history = mountHistory(t);
  history.update({applicationId: 'case-b'});
  await settle();
  assert.equal(firstSignal.aborted, true);
  resolveFirst(Response.json({conversations: [summary('stale-case')]}));
  await settle();
  assert.match(history.html(), /Title correct-case/);
  assert.doesNotMatch(history.html(), /Title stale-case/);
});

test('global history and external refresh use the same validated request path', async t => {
  const urls = [];
  mockFetch(t, async url => {
    urls.push(url);
    return Response.json({conversations: url.includes('/api/conversations?') ? [summary('global')] : []});
  });
  const history = mountHistory(t);
  await settle();
  history.button('Conversations across all applications').props.onClick();
  await settle();
  assert.match(history.html(), /Title global/);
  await history.browser.__refreshChatHistory();
  await settle();
  assert.equal(urls.at(-1), '/api/conversations?limit=50');
});

test('failed deletion keeps saved history and reports its HTTP status', async t => {
  let deletionAttempts = 0;
  mockFetch(t, async (url, options) => {
    if (options.method === 'DELETE') {
      deletionAttempts++;
      return Response.json({detail: 'storage unavailable'}, {status: 503});
    }
    return Response.json({conversations: [summary('keep')]});
  });
  const history = mountHistory(t);
  await settle();
  history.button('Delete').props.onClick({stopPropagation() {}});
  await settle();
  assert.equal(deletionAttempts, 1);
  assert.match(history.html(), /Conversation could not be deleted/);
  assert.match(history.html(), /HTTP 503/);
  assert.deepEqual(history.selections, []);
  history.button('Retry').props.onClick();
  await settle();
  assert.match(history.html(), /Title keep/);
});

test('successful deletion removes only the confirmed conversation and clears its selection', async t => {
  mockFetch(t, async (url, options) => options.method === 'DELETE'
    ? Response.json({success: true})
    : Response.json({conversations: [summary('remove')]}));
  const history = mountHistory(t);
  history.update({currentConversationId: 'remove'});
  await settle();
  history.button('Delete').props.onClick({stopPropagation() {}});
  await settle();
  assert.match(history.html(), /No conversations yet/);
  assert.deepEqual(history.selections, [[null]]);
});

test('deletion completed after a case switch cannot clear the new case selection', async t => {
  let finishDelete;
  mockFetch(t, async (url, options) => {
    if (options.method === 'DELETE') return new Promise(resolve => { finishDelete = resolve; });
    const app = url.includes('case-b') ? 'case-b' : 'case-a';
    return Response.json({conversations: [summary('shared-id', app)]});
  });
  const history = mountHistory(t);
  history.update({currentConversationId: 'shared-id'});
  await settle();
  history.button('Delete').props.onClick({stopPropagation() {}});
  history.update({applicationId: 'case-b', currentConversationId: 'shared-id'});
  await settle();
  finishDelete(Response.json({success: true}));
  await settle();
  assert.match(history.html(), /Title shared-id/);
  assert.deepEqual(history.selections, []);
});

test('an invalid deletion confirmation is not accepted as a successful removal', async t => {
  mockFetch(t, async () => Response.json({success: false}));
  await assert.rejects(api.deleteConversation('case-a', 'keep'),
    error => error.code === 'invalid_conversation_history');
});

test('a late deletion does not clear a different conversation selected in the same case', async t => {
  let finishDelete;
  mockFetch(t, async (url, options) => options.method === 'DELETE'
    ? new Promise(resolve => { finishDelete = resolve; })
    : Response.json({conversations: [summary('old'), summary('new')]}));
  const history = mountHistory(t);
  history.update({currentConversationId: 'old'});
  await settle();
  history.button('Delete').props.onClick({stopPropagation() {}});
  history.update({currentConversationId: 'new'});
  finishDelete(Response.json({success: true}));
  await settle();
  assert.deepEqual(history.selections, []);
});

test('a confirmed deletion is reflected even if the user switches to global history', async t => {
  let finishDelete;
  mockFetch(t, async (url, options) => options.method === 'DELETE'
    ? new Promise(resolve => { finishDelete = resolve; })
    : Response.json({conversations: [summary('remove')]}));
  const history = mountHistory(t);
  history.update({currentConversationId: 'remove'});
  await settle();
  history.button('Delete').props.onClick({stopPropagation() {}});
  history.button('Conversations across all applications').props.onClick();
  await settle();
  finishDelete(Response.json({success: true}));
  await settle();
  assert.match(history.html(), /No conversations found/);
  assert.deepEqual(history.selections, [[null]]);
});

test('collapsed history exposes a failed request and retry rather than hiding the error', async t => {
  mockFetch(t, async () => Response.json({detail: 'unavailable'}, {status: 500}));
  const history = mountHistory(t, {collapsed: true});
  await settle();
  assert.ok(history.button('Retry'));
  assert.match(history.html(), /HTTP 500/);
  assert.match(history.html(), /Unavailable/);
  assert.doesNotMatch(history.html(), /0 chats/);
});

test('history recovery controls and guide instructions exist in all locales', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const messages = JSON.parse(fs.readFileSync(path.join(srcDir, '..', 'messages', `${locale}.json`), 'utf8'));
    const t = createTranslator({locale, messages, namespace: 'chatHistory'});
    assert.ok(t('httpStatus', {status: 404}).includes('404'));
    for (const key of ['retry', 'connectionError', 'invalidResponse', 'deleteError']) {
      assert.notEqual(t(key), `chatHistory.${key}`);
    }
    assert.ok(messages.demoGuide.chatHistoryHelp.includes(t('retry')));
  }
});

test('the real Next proxy forwards both history routes and preserves backend errors', async () => {
  const filename = path.join(srcDir, 'app', 'api', '[...path]', 'route.ts');
  const {outputText} = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
  });
  for (const pathname of [
    'applications/swiss-chocolate-storm/conversations', 'conversations',
  ]) {
    for (const status of [200, 401, 404, 500]) {
      const sourceModule = {exports: {}};
      const payload = status === 200 ? {conversations: []} : {detail: `Backend ${status}`};
      vm.runInNewContext(outputText, {
        module: sourceModule, exports: sourceModule.exports,
        require: name => name === '@/lib/api-base-url'
          ? {getApiBaseUrl: () => 'http://backend.test'} : require(name),
        process: {env: {API_KEY: 'test-only-proxy-key'}},
        console, URL,
        fetch: async (url, options) => {
          assert.equal(url, `http://backend.test/api/${pathname}?limit=50`);
          assert.equal(options.headers['X-API-Key'], 'test-only-proxy-key');
          return Response.json(payload, {status});
        },
      }, {filename});
      const response = await sourceModule.exports.GET(
        new NextRequest(`http://localhost:3138/api/${pathname}?limit=50`),
        {params: Promise.resolve({path: pathname.split('/')})},
      );
      assert.equal(response.status, status);
      assert.deepEqual(await response.json(), payload);
    }
  }
});
