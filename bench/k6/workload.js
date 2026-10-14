// Constant-arrival-rate (open model => no coordinated omission) workloads W1-W5.
// k6 run -e W=w1 -e BASE=http://127.0.0.1:18000 -e RATE=500 -e DURATION=30s -e TOKENS=tokens.json \
//        -e OUT=result.json workload.js
import http from 'k6/http';
import { check } from 'k6';

const W = __ENV.W || 'w1';
const BASE = __ENV.BASE || 'http://127.0.0.1:18000';
const RATE = parseInt(__ENV.RATE || '200');
const DURATION = __ENV.DURATION || '30s';
const BATCH = parseInt(__ENV.BATCH || '100');
const T = JSON.parse(open(__ENV.TOKENS || 'tokens.json'));
const JSON_H = { 'Content-Type': 'application/json' };

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: RATE, timeUnit: '1s', duration: DURATION,
      preAllocatedVUs: Math.min(RATE, 400), maxVUs: 3000,
    },
  },
  summaryTrendStats: ['min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  discardResponseBodies: true,
};

function auth(tok, extra) {
  return { headers: Object.assign({ Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json' }, extra || {}), responseCallback: http.expectedStatuses(200, 201, 202) };
}

function records(n) {
  const now = Date.now() / 1000;
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({
      transformer_id: `TRF-${String(Math.floor(Math.random() * 500)).padStart(4, '0')}`,
      voltage_v: 230 + Math.random() * 8 - 4, current_a: 40 + Math.random() * 10,
      power_factor: 0.85 + Math.random() * 0.15, frequency_hz: 50 + Math.random() * 0.1,
      timestamp_epoch: now - Math.random() * 5,
    });
  }
  return out;
}

export default function () {
  const t = T.tenant[__ITER % T.tenant.length];
  let res;
  switch (W) {
    case 'w1': res = http.get(`${BASE}/health/ready`); break;
    case 'w2': // admin list (superadmin: RLS superadmin branch), paginated
      res = http.get(`${BASE}/api/v1/users?limit=50&skip=${(__ITER % 100) * 50}`, auth(T.super)); break;
    case 'w2t': // tenant-scoped read as a normal user (RLS path when runtime role is non-superuser)
      res = http.get(`${BASE}/api/v1/users/me`, auth(t.token)); break;
    case 'w3': // idempotent write; unique key per request
      res = http.patch(`${BASE}/api/v1/users/me`, JSON.stringify({ full_name: `Bench ${__ITER}` }),
        auth(t.token, { 'Idempotency-Key': `k-${__ENV.RUNID || 'r'}-${__VU}-${__ITER}` })); break;
    case 'w3dup': // same key every time: exercises the replay path
      res = http.patch(`${BASE}/api/v1/users/me`, JSON.stringify({ full_name: 'dup' }),
        auth(t.token, { 'Idempotency-Key': `dup-${__ENV.RUNID || 'r'}-${__ITER % 50}` })); break;
    case 'w4':
      res = http.post(`${BASE}/api/v1/telemetry/ingest`, JSON.stringify(records(BATCH)), auth(T.super)); break;
    case 'w5': // login (Argon2id)
      res = http.post(`${BASE}/api/v1/auth/login`,
        JSON.stringify({ email: T.emails[__ITER % T.emails.length], password: 'BenchPass123!' }),
        { headers: JSON_H, responseCallback: http.expectedStatuses(200, 201) }); break;
    default: throw new Error('unknown W ' + W);
  }
  check(res, { ok: (r) => r.status >= 200 && r.status < 300 });
}

export function handleSummary(d) {
  const m = d.metrics;
  const dur = m.http_req_duration.values;
  const secs = d.state.testRunDurationMs / 1000;
  const out = {
    workload: W, base: BASE, target_rate: RATE, batch: BATCH,
    achieved_rps: m.http_reqs.values.count / secs,
    requests: m.http_reqs.values.count,
    dropped_iterations: (m.dropped_iterations || { values: { count: 0 } }).values.count,
    error_rate: m.http_req_failed.values.rate,
    p50_ms: dur.med, p90_ms: dur['p(90)'], p95_ms: dur['p(95)'], p99_ms: dur['p(99)'], max_ms: dur.max,
    max_vus: m.vus_max ? m.vus_max.values.max : null,
  };
  const o = {};
  o[__ENV.OUT || 'result.json'] = JSON.stringify(out, null, 2);
  o.stdout = `${W} rate=${RATE} rps=${out.achieved_rps.toFixed(1)} p50=${out.p50_ms.toFixed(1)} p95=${out.p95_ms.toFixed(1)} p99=${out.p99_ms.toFixed(1)} max=${out.max_ms.toFixed(0)} err=${(out.error_rate * 100).toFixed(2)}% dropped=${out.dropped_iterations}\n`;
  return o;
}
