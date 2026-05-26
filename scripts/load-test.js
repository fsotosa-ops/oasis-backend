/**
 * k6 Load Test — Cloud Run staging
 *
 * Two modes:
 *
 *   MODE 1 — "Token mode" (recommended for Cloud Run):
 *     Login manually once, pass the JWT token. Avoids rate limiting issues.
 *     k6 run --env BASE_URL=https://oasis-backend-xxx.run.app \
 *            --env TOKEN=eyJhbG... \
 *            scripts/load-test.js
 *
 *   MODE 2 — "Login mode" (full flow):
 *     Each VU logs in. Requires rate limit raised in staging.
 *     k6 run --env BASE_URL=https://oasis-backend-xxx.run.app \
 *            --env TEST_EMAIL=loadtest@example.com \
 *            --env TEST_PASSWORD=Test1234! \
 *            scripts/load-test.js
 *
 * Options:
 *   --env MAX_VUS=500        Max virtual users (default: 200)
 *   --env FRONTEND_URL=...   Also test frontend Cloud Run (optional)
 *
 * How to get your TOKEN:
 *   1. Open your staging app in browser
 *   2. DevTools → Application → Local Storage → find sb-*-auth-token
 *   3. Copy the access_token value
 *   — OR —
 *   curl -s -X POST https://your-backend.run.app/api/v1/auth/login \
 *     -H 'Content-Type: application/json' \
 *     -d '{"email":"tu@email.com","password":"tupassword"}' | jq -r .access_token
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const FRONTEND_URL = __ENV.FRONTEND_URL || '';
const API = `${BASE_URL}/api/v1`;
const MAX_VUS = parseInt(__ENV.MAX_VUS || '200');
const TOKEN = __ENV.TOKEN || '';

// Custom metrics
const dashboardSuccess = new Rate('dashboard_success');
const dashboardDuration = new Trend('dashboard_duration', true);
const healthDuration = new Trend('health_duration', true);

// ---------------------------------------------------------------------------
// Stages: ramp-up → hold → spike → hold → ramp-down
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: '30s', target: 50 },                      // Warm-up
    { duration: '1m', target: Math.min(MAX_VUS, 200) },   // Ramp to 200
    { duration: '3m', target: Math.min(MAX_VUS, 200) },   // Hold at 200
    { duration: '1m', target: MAX_VUS },                   // Ramp to MAX
    { duration: '3m', target: MAX_VUS },                   // Hold at MAX
    { duration: '1m', target: 0 },                         // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],   // 95% of requests under 3s
    http_req_failed: ['rate<0.01'],      // Error rate under 1%
    dashboard_success: ['rate>0.95'],    // 95%+ dashboard loads succeed
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function authHeaders(token) {
  return {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  };
}

function getToken() {
  // Mode 1: pre-supplied token
  if (TOKEN) return TOKEN;

  // Mode 2: login per VU
  const email = __ENV.TEST_EMAIL;
  const password = __ENV.TEST_PASSWORD;
  if (!email || !password) {
    console.error('ERROR: Set either TOKEN or TEST_EMAIL+TEST_PASSWORD');
    return null;
  }

  const res = http.post(
    `${API}/auth/login`,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } }
  );

  if (res.status === 429) {
    // Rate limited — wait and skip this iteration
    sleep(5);
    return null;
  }

  const ok = check(res, { 'login 200': (r) => r.status === 200 });
  if (!ok) return null;

  try {
    return res.json().access_token;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Setup: login once (shared across VUs in token mode)
// ---------------------------------------------------------------------------
export function setup() {
  // Verify backend is reachable
  const health = http.get(`${BASE_URL}/health`);
  const ok = check(health, { 'backend reachable': (r) => r.status === 200 });
  if (!ok) {
    console.error(`Backend not reachable at ${BASE_URL}/health`);
  } else {
    const data = health.json();
    console.log(`Backend: ${data.status} | Redis: ${data.redis}`);
  }

  // Verify frontend if provided
  if (FRONTEND_URL) {
    const fHealth = http.get(FRONTEND_URL, { redirects: 0 });
    check(fHealth, { 'frontend reachable': (r) => r.status < 400 });
  }

  return { token: TOKEN };
}

// ---------------------------------------------------------------------------
// Main scenario — each VU iteration
// ---------------------------------------------------------------------------
export default function (data) {
  const token = data.token || getToken();

  if (!token) {
    sleep(2);
    return;
  }

  // --- 1. Backend: Health check ---
  group('Health', function () {
    const res = http.get(`${BASE_URL}/health`, {
      tags: { name: 'health' },
    });
    healthDuration.add(res.timings.duration);
    check(res, { 'health 200': (r) => r.status === 200 });
  });

  sleep(0.3);

  // --- 2. Backend: Dashboard batch (the heaviest real endpoint) ---
  group('Dashboard', function () {
    const res = http.get(
      `${API}/journeys/enrollments/me/full`,
      Object.assign({ tags: { name: 'dashboard_batch' } }, authHeaders(token))
    );
    dashboardDuration.add(res.timings.duration);
    const ok = check(res, {
      'dashboard 200': (r) => r.status === 200,
      'dashboard has data': (r) => {
        try { return Array.isArray(r.json()); } catch { return r.status === 200; }
      },
    });
    dashboardSuccess.add(ok);
  });

  sleep(0.3);

  // --- 3. Frontend: load main page (if URL provided) ---
  if (FRONTEND_URL) {
    group('Frontend', function () {
      const res = http.get(FRONTEND_URL, {
        tags: { name: 'frontend_page' },
        redirects: 5,
      });
      check(res, { 'frontend 200': (r) => r.status === 200 });
    });
  }

  // Simulate user reading the dashboard (2-5s)
  sleep(Math.random() * 3 + 2);
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  const get = (key, sub) => {
    try { return data.metrics[key].values[sub]; } catch { return null; }
  };

  const p50 = get('http_req_duration', 'p(50)');
  const p95 = get('http_req_duration', 'p(95)');
  const p99 = get('http_req_duration', 'p(99)');
  const errRate = get('http_req_failed', 'rate');
  const dashRate = get('dashboard_success', 'rate');
  const reqs = get('http_reqs', 'count');
  const rps = get('http_reqs', 'rate');

  const fmt = (v, suffix) => (v !== null ? (typeof v === 'number' ? v.toFixed(0) + suffix : v) : 'N/A');

  console.log('\n' + '='.repeat(60));
  console.log('  LOAD TEST RESULTS');
  console.log('='.repeat(60));
  console.log(`  Total requests:    ${fmt(reqs, '')}`);
  console.log(`  Requests/sec:      ${fmt(rps, '/s')}`);
  console.log(`  p50 latency:       ${fmt(p50, 'ms')}`);
  console.log(`  p95 latency:       ${fmt(p95, 'ms')}`);
  console.log(`  p99 latency:       ${fmt(p99, 'ms')}`);
  console.log(`  Error rate:        ${errRate !== null ? (errRate * 100).toFixed(2) + '%' : 'N/A'}`);
  console.log(`  Dashboard success: ${dashRate !== null ? (dashRate * 100).toFixed(1) + '%' : 'N/A'}`);
  console.log('-'.repeat(60));

  const pass = p95 !== null && p95 < 3000 && errRate !== null && errRate < 0.01;
  console.log(pass ? '  VERDICT: PASS' : '  VERDICT: FAIL');
  console.log('='.repeat(60) + '\n');

  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
