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
      console, URL, URLSearchParams, TextEncoder, Buffer, AbortSignal, crypto: webcrypto,
      fetch: env.fetch,
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

test('multitenant sign-in requires an explicit tenant allowlist', () => {
  const { policy } = loadAuth({ ...entra, ENTRA_TENANT_ID: 'organizations' });
  assert.equal(policy.isEntraEnabled(), false);
  const restricted = loadAuth({
    ...entra, ENTRA_TENANT_ID: 'organizations', ENTRA_ALLOWED_TENANT_IDS: 'corporate-tenant',
  });
  assert.equal(restricted.policy.isEntraEnabled(), true);
});

test('Entra administrators must be explicitly authorized, not inferred from their name', () => {
  const { auth } = loadAuth({ ...entra, ACCESS_ADMIN_EMAILS: 'owner@example.com' });
  assert.equal(auth.isEntraAdminEmail('owner@example.com'), true);
  assert.equal(auth.isEntraAdminEmail('prevaiq-admin-stranger@example.com'), false);
});

test('organization token exchange accepts only the allowed tenant and validates claims', async () => {
  const { createHash } = require('node:crypto');
  const state = 'test-state';
  const claims = {
    aud: 'test-client', tid: 'corporate-tenant',
    iss: 'https://login.microsoftonline.com/corporate-tenant/v2.0',
    nonce: createHash('sha256').update(state).digest('base64url'),
    exp: Math.floor(Date.now() / 1000) + 600,
    preferred_username: 'colleague@example.com', name: 'Colleague',
  };
  const { load } = loadAuth({
    ...entra, ENTRA_TENANT_ID: 'organizations', ENTRA_ALLOWED_TENANT_IDS: 'corporate-tenant',
    fetch: async () => ({
      ok: true, json: async () => ({
        id_token: `header.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.signature`,
      }),
    }),
  });

  const oidc = load('lib/entra');
  const cfg = oidc.entraConfig();
  const exchange = () => oidc.exchangeCode(cfg, 'https://demo.example.com', 'code', state);
  assert.equal(new URL(oidc.authorizeUrl(cfg, 'https://demo.example.com', state)).pathname,
    '/organizations/oauth2/v2.0/authorize');
  assert.equal((await exchange()).email, 'colleague@example.com');
  for (const tenant of ['other-tenant', '9188040d-6c67-4c5b-b112-36a304b66dad']) {
    claims.tid = tenant;
    claims.iss = `https://login.microsoftonline.com/${tenant}/v2.0`;
    assert.equal(await exchange(), null);
  }
  claims.tid = 'corporate-tenant';
  claims.iss = 'https://login.microsoftonline.com/corporate-tenant/v2.0';
  for (const [key, invalid] of [['aud', 'other-client'], ['nonce', 'wrong'], ['exp', 0], ['iss', 'wrong']]) {
    const original = claims[key];
    claims[key] = invalid;
    assert.equal(await exchange(), null);
    claims[key] = original;
  }
});

test('callback records pending colleagues but grants a session only after approval', async () => {
    const { createHash } = require('node:crypto');
    const state = 'callback-test';
    const claims = {
      aud: 'test-client', tid: 'corporate-tenant',
      iss: 'https://login.microsoftonline.com/corporate-tenant/v2.0',
      nonce: createHash('sha256').update(state).digest('base64url'),
      exp: Math.floor(Date.now() / 1000) + 600, preferred_username: 'colleague@example.com',
    };
    for (const status of [null, 'pending', 'approved', 'refused']) {
      const calls = [];
      const { load } = loadAuth({
        NODE_ENV: 'production', ...entra, ENTRA_TENANT_ID: 'organizations',
        ENTRA_ALLOWED_TENANT_IDS: 'corporate-tenant',
        fetch: async (url, options) => {
          calls.push([url, options]);
          if (url.includes('/token')) return {
            ok: true, json: async () => ({
              id_token: `h.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.s`,
            }),
          };
          return { ok: true, json: async () => ({ status }) };
        },
      });
      const response = await load('app/api/auth/entra/callback/route').GET(new NextRequest(
        `https://demo.example.com/api/auth/entra/callback?code=code&state=${state}`,
        { headers: { host: 'demo.example.com', cookie: `entra_state=${state}` } }
      ));
      const target = new URL(response.headers.get('location'));
      if (status === 'approved') {
        assert.equal(target.pathname, '/');
        assert.ok(response.cookies.get('session'));
      } else {
        assert.equal(target.pathname, '/access');
        assert.equal(target.searchParams.get('state'), status === 'refused' ? 'refused' : 'pending');
        assert.equal(response.cookies.get('session'), undefined);
      }
      assert.equal(calls.some(([url]) => url.endsWith('/request')), status === null || status === 'pending');
    }
  });

test('invalid state and Entra errors never create requests', async () => {
    const calls = [];
    const { load } = loadAuth({
      ...entra, fetch: async (url) => { calls.push(url); throw new Error('must not fetch'); },
    });
    const callback = load('app/api/auth/entra/callback/route');
    for (const query of ['code=code&state=missing-cookie', 'error=access_denied']) {
      const response = await callback.GET(new NextRequest(
        `https://demo.example.com/api/auth/entra/callback?${query}`,
        { headers: { host: 'demo.example.com' } }
      ));
      assert.equal(new URL(response.headers.get('location')).pathname, '/login');
      assert.equal(response.cookies.get('session'), undefined);
    }
    assert.equal(calls.length, 0);
  });

test('corporate and sandbox access keeps tenant, approval and administrator gates separate', async (t) => {
  const { createHash } = require('node:crypto');
  const state = 'technical-access-state';
  const scenarios = [
    { name: 'corporate administrator bypasses pending requests', tenant: 'corporate-tenant',
      upn: 'owner@example.com', status: 'pending', role: 'admin' },
    { name: 'explicit technical administrator bypasses pending requests', tenant: 'sandbox-tenant',
      upn: 'TECHNICAL-ADMIN@sandbox.example', status: 'pending', role: 'admin' },
    { name: 'approved technical user gets no administrator access', tenant: 'sandbox-tenant',
      upn: 'technical-user@sandbox.example', status: 'approved', role: 'entra' },
    { name: 'second approved technical user gets no administrator access', tenant: 'sandbox-tenant',
      upn: 'technical-user2@sandbox.example', status: 'approved', role: 'entra' },
    { name: 'approved corporate colleague still signs in', tenant: 'corporate-tenant',
      upn: 'colleague@example.com', status: 'approved', role: 'entra' },
    { name: 'other sandbox users still need approval', tenant: 'sandbox-tenant',
      upn: 'other@sandbox.example', status: null, pending: true },
    { name: 'an administrator address does not bypass a disallowed tenant', tenant: 'other-tenant',
      upn: 'technical-admin@sandbox.example', status: 'approved', rejected: true },
    { name: 'optional email claim cannot impersonate the technical administrator', tenant: 'sandbox-tenant',
      upn: 'technical-user@sandbox.example', email: 'technical-admin@sandbox.example',
      status: 'approved', role: 'entra' },
  ];
  for (const scenario of scenarios) {
    await t.test(scenario.name, async () => {
      const calls = [];
      const claims = {
        aud: 'test-client', tid: scenario.tenant,
        iss: `https://login.microsoftonline.com/${scenario.tenant}/v2.0`,
        nonce: createHash('sha256').update(state).digest('base64url'),
        exp: Math.floor(Date.now() / 1000) + 600,
        preferred_username: scenario.upn, email: scenario.email,
      };
      const { auth, load } = loadAuth({
        NODE_ENV: 'production', ...entra, ENTRA_TENANT_ID: 'organizations',
        ENTRA_ALLOWED_TENANT_IDS: 'corporate-tenant, sandbox-tenant',
        ACCESS_ADMIN_EMAILS: 'owner@example.com, TECHNICAL-ADMIN@sandbox.example ',
        fetch: async (url) => {
          calls.push(url);
          if (url.includes('/token')) return {
            ok: true, json: async () => ({
              id_token: `h.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.s`,
            }),
          };
          return { ok: true, json: async () => ({ status: scenario.status }) };
        },
      });
      const response = await load('app/api/auth/entra/callback/route').GET(new NextRequest(
        `https://demo.example.com/api/auth/entra/callback?code=code&state=${state}`,
        { headers: { host: 'demo.example.com', cookie: `entra_state=${state}` } }
      ));
      const target = new URL(response.headers.get('location'));
      const session = response.cookies.get('session');
      const accessCalls = calls.filter((url) => url.includes('/api/internal/access'));
      if (scenario.rejected) {
        assert.equal(target.pathname, '/login');
        assert.equal(session, undefined);
        assert.equal(accessCalls.length, 0);
      } else if (scenario.pending) {
        assert.equal(target.pathname, '/access');
        assert.equal(target.searchParams.get('state'), 'pending');
        assert.equal(session, undefined);
        assert.ok(accessCalls.some((url) => url.endsWith('/request')));
      } else {
        assert.equal(target.pathname, '/');
        assert.ok(session);
        const username = auth.validateSessionToken(session.value);
        assert.equal(auth.displayName(username), scenario.upn.toLowerCase());
        assert.equal(auth.sessionRole(username), scenario.role);
        const adminPage = await load('proxy').proxy(new NextRequest('https://demo.example.com/admin', {
          headers: { cookie: `session=${session.value}` },
        }));
        if (scenario.role === 'admin') {
          assert.equal(accessCalls.length, 0);
          assert.equal(adminPage.headers.get('x-middleware-next'), '1');
        } else {
          assert.equal(new URL(adminPage.headers.get('location')).pathname, '/');
        }
      }
    });
  }
});
