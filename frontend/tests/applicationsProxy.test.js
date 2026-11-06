const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const { NextRequest } = require('next/server');

const root = path.resolve(__dirname, '..');

function loadRoute(relative, fetch) {
  const filename = path.join(root, 'src', 'app', 'api', 'applications', relative);
  const sourceModule = { exports: {} };
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  vm.runInNewContext(outputText, {
    module: sourceModule,
    exports: sourceModule.exports,
    require: (name) => name === '@/lib/api-base-url'
      ? { getApiBaseUrl: () => 'http://backend.test' }
      : require(name),
    process: { env: {} },
    console: { error() {} },
    fetch,
  }, { filename });
  return sourceModule.exports;
}

for (const persona of ['underwriting', 'automotive_claims']) {
  test(`${persona}: backend failure is not replaced with a phantom demo case`, async () => {
    const route = loadRoute('route.ts', async () => { throw new Error('offline'); });
    const response = await route.GET(new NextRequest(
      `http://localhost:3102/api/applications?persona=${persona}`
    ));
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), { error: 'Application service is unavailable' });
  });

  test(`${persona}: list queries and real case data pass through`, async () => {
    const cases = [{ id: `${persona}-demo`, persona }];
    const route = loadRoute('route.ts', async (url) => {
      assert.equal(url, `http://backend.test/api/applications?persona=${persona}`);
      return Response.json(cases);
    });
    const response = await route.GET(new NextRequest(
      `http://localhost:3102/api/applications?persona=${persona}`
    ));
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), cases);
  });
}

for (const status of [401, 403, 404, 503]) {
  test(`case detail preserves backend status ${status} instead of reading local files`, async () => {
    const route = loadRoute(path.join('[id]', 'route.ts'), async () => (
      Response.json({ detail: 'Backend error' }, { status })
    ));
    const response = await route.GET(
      new NextRequest('http://localhost:3102/api/applications/demo'),
      { params: Promise.resolve({ id: 'demo' }) }
    );
    assert.equal(response.status, status);
    assert.deepEqual(await response.json(), { detail: 'Backend error' });
  });
}

test('case detail reports an unavailable backend as 502, not a missing case', async () => {
  const route = loadRoute(path.join('[id]', 'route.ts'), async () => { throw new Error('offline'); });
  const response = await route.GET(
    new NextRequest('http://localhost:3102/api/applications/demo'),
    { params: Promise.resolve({ id: 'demo' }) }
  );
  assert.equal(response.status, 502);
});

for (const language of ['de', 'de-CH']) {
  test(`case detail forwards ${language} without dropping locale or source-page query options`, async () => {
    const query = `language=${language}&page=12`;
    const route = loadRoute(path.join('[id]', 'route.ts'), async (url) => {
      assert.equal(url, `http://backend.test/api/applications/demo?${query}`);
      return Response.json({ id: 'demo', analysis_language: 'de' });
    });
    const response = await route.GET(
      new NextRequest(`http://localhost:3102/api/applications/demo?${query}`),
      { params: Promise.resolve({ id: 'demo' }) }
    );
    assert.equal(response.status, 200);
    assert.equal((await response.json()).analysis_language, 'de');
  });
}
