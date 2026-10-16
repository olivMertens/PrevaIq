const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const ts = require('typescript');
const { NextRequest } = require('next/server');

const src = path.resolve(__dirname, '..', 'src');
const entra = {
  ENTRA_TENANT_ID: 'test-tenant',
  ENTRA_CLIENT_ID: 'test-client',
  ENTRA_CLIENT_SECRET: 'test-secret',
};

// Isolate environment and module state without changing the test process's credentials.
function loadAuth(env) {
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const sourceModule = { exports: {} };
    cache.set(filename, sourceModule.exports);
    const nativeRequire = createRequire(filename);
    const requireSource = (name) => {
      if (name.startsWith('@/') || name.startsWith('.')) {
        const target = name.startsWith('@/')
          ? path.join(src, name.slice(2))
          : path.resolve(path.dirname(filename), name);
        return load(`${target}.ts`);
      }
      return nativeRequire(name);
    };
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    });
    vm.runInNewContext(outputText, {
      module: sourceModule, exports: sourceModule.exports, require: requireSource, process: { env },
      console, URL, TextEncoder, crypto: webcrypto,
    }, { filename });
    return sourceModule.exports;
  }
  return {
    auth: load(path.join(src, 'lib', 'auth.ts')),
    policy: load(path.join(src, 'lib', 'auth-config.ts')),
    load: (name) => load(path.join(src, `${name}.ts`)),
  };
}

function request(pathname, token) {
  return new NextRequest(`http://localhost:3000${pathname}`, {
    headers: token ? { cookie: `session=${token}` } : undefined,
  });
}

test('production ignores local credentials and opt-in flag', () => {
  const { auth, policy } = loadAuth({
    NODE_ENV: 'production', LOCAL_AUTH_ENABLED: 'true', AUTH_USER_1: 'demo:password',
  });
  assert.equal(policy.isAuthEnabled(), true);
  assert.equal(policy.isLocalAuthEnabled(), false);
  assert.equal(auth.getUsers().size, 0);
  assert.equal(auth.findUser('demo'), null);
});

test('development requires explicit opt-in even with existing credentials', () => {
  const { auth, policy } = loadAuth({ NODE_ENV: 'development', AUTH_USER_1: 'demo:password' });
  assert.equal(policy.isLocalAuthEnabled(), false);
  assert.equal(policy.isAuthEnabled(), false);
  assert.equal(auth.getUsers().size, 0);
});

test('opted-in development preserves username normalization and colon passwords', () => {
  const { auth, policy } = loadAuth({
    NODE_ENV: 'development', LOCAL_AUTH_ENABLED: 'true', AUTH_USER_1: 'Demo:pass:word',
  });
  assert.equal(policy.isAuthEnabled(), true);
  const user = auth.findUser(' DEMO ');
  assert.equal(user.username, 'Demo');
  assert.equal(user.password, 'pass:word');
  assert.equal(auth.validateSessionToken(auth.createSessionToken('Demo')), 'Demo');
});

test('production rejects old signed local sessions and preserves Entra roles', () => {
  const { auth } = loadAuth({ NODE_ENV: 'production', ...entra });
  assert.equal(auth.validateSessionToken(auth.createSessionToken('prevaIqAdmin')), null);
  for (const username of ['entra:user@example.com', 'entra-admin:admin@example.com']) {
    assert.equal(auth.validateSessionToken(auth.createSessionToken(username)), username);
  }
  assert.equal(auth.sessionRole('entra:user@example.com'), 'entra');
  assert.equal(auth.sessionRole('entra-admin:admin@example.com'), 'admin');
});

test('production without Entra fails closed in proxy and rejects signed sessions', async () => {
  const { auth, load } = loadAuth({ NODE_ENV: 'production' });
  const { proxy } = load('proxy');
  const response = await proxy(request('/'));
  assert.equal(new URL(response.headers.get('location')).pathname, '/login');
  assert.equal(auth.validateSessionToken(auth.createSessionToken('entra:user@example.com')), null);
});

test('proxy rejects legacy admin cookie but accepts Entra admin and protects administration', async () => {
  const { auth, load } = loadAuth({ NODE_ENV: 'production', ...entra });
  const { proxy } = load('proxy');
  const legacy = await proxy(request('/admin', auth.createSessionToken('prevaIqAdmin')));
  assert.equal(new URL(legacy.headers.get('location')).pathname, '/login');
  const admin = await proxy(request('/admin', auth.createSessionToken('entra-admin:a@example.com')));
  assert.equal(admin.headers.get('x-middleware-next'), '1');
  const user = await proxy(request('/admin', auth.createSessionToken('entra:u@example.com')));
  assert.equal(new URL(user.headers.get('location')).pathname, '/');
});

test('password endpoint is disabled in production and non-opted-in development', async () => {
  for (const NODE_ENV of ['production', 'development']) {
    const { load } = loadAuth({ NODE_ENV, AUTH_USER_1: 'demo:password', ...entra });
    const response = await load('app/api/auth/login/route').POST(request('/api/auth/login'));
    assert.equal(response.status, 403);
  }
});

test('development password endpoint still signs in opted-in users', async () => {
  const { load } = loadAuth({
    NODE_ENV: 'development', LOCAL_AUTH_ENABLED: 'true', AUTH_USER_1: 'Demo:pass:word',
  });
  const response = await load('app/api/auth/login/route').POST(new NextRequest(
    'http://localhost:3000/api/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: ' DEMO ', password: 'pass:word' }),
    }
  ));
  assert.equal(response.status, 200);
  assert.ok(response.cookies.get('session')?.value);
  assert.equal((await response.json()).username, 'Demo');
});

test('provider response advertises Entra only and rejects legacy cookie', async () => {
  const { auth, load } = loadAuth({ NODE_ENV: 'production', ...entra });
  const response = await load('app/api/auth/check/route').GET(
    request('/api/auth/check', auth.createSessionToken('prevaIqAdmin'))
  );
  assert.equal(response.status, 401);
  const data = await response.json();
  assert.equal(data.entraEnabled, true);
  assert.equal(data.localAuthEnabled, false);
  assert.equal(data.authEnabled, true);
});

test('health reports providers rather than legacy account diagnostics', async () => {
  const { load } = loadAuth({ NODE_ENV: 'production', ...entra });
  const response = await load('app/api/health/route').GET();
  const data = await response.json();
  assert.equal(data.auth.entraEnabled, true);
  assert.equal(data.auth.localAuthEnabled, false);
  assert.equal(data.debug, undefined);
});
