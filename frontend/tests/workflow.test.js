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

const chatDir = path.join(srcDir, 'components', 'chat');
const { agentDisplayText } = load('agentText.ts', chatDir);
const { readWorkflowResponse, updateWorkflowExecution } = load('workflowStream.ts', path.join(srcDir, 'lib'));
const messages = locale => JSON.parse(fs.readFileSync(path.join(srcDir, '..', 'messages', `${locale}.json`), 'utf8'));
const finalResult = {
  workflow: 'express', status: 'completed',
  steps: [{ agent: 'ExtractAgent', text: 'Marie Lefèvre' }, { agent: 'PolicyAgent', text: 'Article C1' }, { agent: 'DecisionAgent', text: 'Review the documents.' }],
  summary: 'Review the documents.',
  plan: [{ id: 'context', agents: [] }, { id: 'parallel', agents: ['ExtractAgent', 'PolicyAgent'] }, { id: 'synthesis', agents: ['DecisionAgent'] }],
};
const frame = value => `data: ${JSON.stringify(value)}\r\n\r\n`;

function streamResponse(text, chunkSize = 7) {
  const bytes = new TextEncoder().encode(text);
  let index = 0;
  return new Response(new ReadableStream({
    pull(controller) {
      if (index >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(index, index + chunkSize));
      index += chunkSize;
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } });
}

test('live progress is delivered before the final result, even across UTF-8 and CRLF boundaries', async () => {
  let send;
  const seen = [];
  let settled = false;
  const response = new Response(new ReadableStream({ start(controller) { send = controller; } }), {
    headers: { 'Content-Type': 'text/event-stream' },
  });
  const reading = readWorkflowResponse(response, event => seen.push(event)).then(value => { settled = true; return value; });
  send.enqueue(new TextEncoder().encode(frame({ type: 'step', agent: 'ExtractAgent', status: 'running' })));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(seen.length, 1);
  assert.equal(settled, false);
  send.enqueue(new TextEncoder().encode(frame({ type: 'done', result: finalResult })));
  assert.deepEqual(await reading, finalResult);
  const utf8 = { ...finalResult, summary: 'Marie Lefèvre — geprüft' };
  assert.deepEqual(await readWorkflowResponse(streamResponse(`: keepalive\r\n\r\n${frame({ type: 'done', result: utf8 })}`, 1), () => {}), utf8);
});

test('failed, malformed and prematurely closed streams never become completed workflows', async () => {
  for (const text of [
    frame({ type: 'error', status: 503, detail: { code: 'AI_UNAVAILABLE' } }),
    frame({ type: 'step', agent: 'ExtractAgent', status: 'invented' }),
    frame({ type: 'done', result: { ...finalResult, summary: '' } }),
    frame({ type: 'step', agent: 'ExtractAgent', status: 'running' }),
  ]) {
    await assert.rejects(readWorkflowResponse(streamResponse(text), () => {}));
  }
  await assert.rejects(readWorkflowResponse(Response.json({ detail: 'Unavailable' }, { status: 503 }), () => {}), error => error.status === 503);
  assert.deepEqual(await readWorkflowResponse(Response.json(finalResult), () => {}), finalResult);
});

test('execution state tracks independent agents without advancing the synthesizer on a timer', () => {
  let execution = { plan: [], context: 'waiting', agents: {} };
  for (const event of [
    { type: 'plan', plan: finalResult.plan },
    { type: 'stage', id: 'context', status: 'completed' },
    { type: 'step', agent: 'ExtractAgent', status: 'running' },
    { type: 'step', agent: 'PolicyAgent', status: 'running' },
    { type: 'step', agent: 'ExtractAgent', status: 'failed', duration_ms: 30 },
  ]) execution = updateWorkflowExecution(execution, event);
  assert.equal(execution.agents.ExtractAgent.status, 'failed');
  assert.equal(execution.agents.PolicyAgent.status, 'running');
  assert.equal(execution.agents.DecisionAgent, undefined);
  assert.equal(execution.context, 'completed');
});

test('legacy machine headings are localized without changing names, filenames, quotes or code', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const t = createTranslator({ locale, messages: messages(locale), namespace: 'chat' });
    const source = '**Conditions_or_franchise**\nMarie Lefèvre / IMG_20260831_100512.jpg / CHF 50’000\n\n### Next_steps\n- Review Article C1\n> Next_steps\n```text\nNext_steps\n```';
    const displayed = agentDisplayText(source, t);
    assert.ok(displayed.includes(t('decisionFields.conditionsOrDeductible')));
    assert.ok(displayed.includes(t('decisionFields.nextSteps')));
    assert.ok(displayed.includes('Marie Lefèvre / IMG_20260831_100512.jpg / CHF 50’000'));
    assert.ok(displayed.includes('> Next_steps'));
    assert.ok(displayed.includes('```text\nNext_steps\n```'));
    const json = agentDisplayText(JSON.stringify({ decision: 'review_needed', rationale: 'Article C1', next_steps: ['Request invoices'] }), t);
    assert.ok(json.indexOf(t('decisionFields.nextSteps')) < json.indexOf(t('decisionFields.rationale')));
  }
});

function component(name, locale, cache = new Map()) {
  if (cache.has(name)) return cache.get(name);
  const filename = path.join(chatDir, name);
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  const module = { exports: {} };
  const localRequire = specifier => {
    if (specifier === 'next-intl') return { useTranslations: namespace => createTranslator({ locale, messages: messages(locale), namespace }) };
    if (specifier === './ChatCards') return { StructuredContentRenderer: ({ content }) => React.createElement('p', null, content) };
    if (specifier === './agentText') return { agentDisplayText };
    if (specifier.startsWith('.')) return component(`${specifier.slice(2)}.tsx`, locale, cache);
    return require(specifier);
  };
  vm.runInThisContext(`(function(module, exports, require) {${outputText}\n})`, { filename })(module, module.exports, localRequire);
  cache.set(name, module.exports);
  return module.exports;
}

test('workflow result shows summary first, the ordered plan, role icons and expandable findings in each locale', () => {
  for (const locale of ['en', 'fr', 'de']) {
    const Result = component('WorkflowResult.tsx', locale).default;
    const execution = { plan: finalResult.plan, context: 'completed', agents: Object.fromEntries(finalResult.steps.map(step => [step.agent, { status: 'completed' }])) };
    const html = renderToStaticMarkup(React.createElement(Result, {
      result: { id: 'express', name: 'Express', status: 'completed', steps: finalResult.steps, summary: finalResult.summary, durationMs: 1000, execution },
    }));
    const catalog = messages(locale).chat;
    assert.ok(html.indexOf(finalResult.summary) < html.indexOf(catalog.workflowPlanTitle));
    assert.ok(html.indexOf(catalog.workflowStages.context) < html.indexOf(catalog.workflowStages.parallel));
    assert.ok(html.indexOf(catalog.workflowStages.parallel) < html.indexOf(catalog.workflowStages.synthesis));
    assert.ok(html.includes(catalog.workflowRoles.extraction));
    assert.ok(html.includes(catalog.workflowRoles.policy));
    assert.ok(html.includes('<svg'));
    assert.ok(html.includes('<details'));
  }
});
