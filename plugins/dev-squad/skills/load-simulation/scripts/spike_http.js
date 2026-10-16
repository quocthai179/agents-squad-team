// k6 spike-test template for sudden traffic bursts (open model: ramping-arrival-rate).
// Copy into the project (e.g. .squad/perf/<scenario>/spike.js) and adapt `request()`.
//
//   k6 run -e BASE_URL=http://localhost:8080 spike.js
//   k6 run -e BASE_URL=http://localhost:8080 -e BASE=20 -e PEAK=800 -e HOLD=60s spike.js
//   k6 run -e BASE_URL=... -e STAGES='[{"duration":"30s","target":20},{"duration":"5s","target":800}]' spike.js
//
// Safety: refuses non-local hosts unless ALLOW_HOSTS contains the host.
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const BASE = Number(__ENV.BASE || 20);         // baseline req/s
const PEAK = Number(__ENV.PEAK || 500);        // spike req/s
const WARMUP = __ENV.WARMUP || '30s';
const HOLD = __ENV.HOLD || '60s';
const RECOVERY = __ENV.RECOVERY || '60s';
const ALLOW_HOSTS = (__ENV.ALLOW_HOSTS || '').split(',').filter(Boolean);
const LOCAL = ['localhost', '127.0.0.1', '::1', 'host.docker.internal'];

const host = BASE_URL.replace(/^https?:\/\//, '').split(/[/:]/)[0];
if (!LOCAL.includes(host) && !ALLOW_HOSTS.includes(host)) {
  throw new Error(`Refusing to load-test non-local host '${host}'. Set ALLOW_HOSTS=${host} if you own it (never production without approval).`);
}

// Instant jump (1s) to PEAK, hold, drop back: does the service absorb it and recover?
const stages = __ENV.STAGES ? JSON.parse(__ENV.STAGES) : [
  { duration: WARMUP, target: BASE },
  { duration: '1s', target: PEAK },
  { duration: HOLD, target: PEAK },
  { duration: '1s', target: BASE },
  { duration: RECOVERY, target: BASE },
];

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate', // arrivals keep coming even when the service slows down
      startRate: BASE,
      timeUnit: '1s',
      preAllocatedVUs: Math.max(50, Math.ceil(PEAK / 4)),
      maxVUs: Math.max(200, PEAK * 2),
      stages,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    dropped_iterations: ['count<1'], // k6 could not start iterations on time = saturation
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const errorsByStatus = new Counter('errors_by_status');
const hotKeyLatency = new Trend('hot_key_latency', true);

// Skewed key distribution: a few keys get most of the traffic (hot rows / cache keys).
function zipf(n, s) {
  let total = 0;
  for (let k = 1; k <= n; k++) total += 1 / Math.pow(k, s);
  let r = Math.random() * total;
  for (let k = 1; k <= n; k++) {
    r -= 1 / Math.pow(k, s);
    if (r <= 0) return k;
  }
  return n;
}

function request() {
  // ADAPT: replace with the real hot endpoint(s) and payloads from the codebase.
  const id = zipf(1000, 1.2);
  const res = http.get(`${BASE_URL}/api/items/${id}`, { tags: { name: 'GET /api/items/:id' } });
  if (id <= 10) hotKeyLatency.add(res.timings.duration);
  return res;
}

export default function () {
  const res = request();
  const ok = check(res, { 'status is 2xx/3xx': (r) => r.status >= 200 && r.status < 400 });
  if (!ok) errorsByStatus.add(1, { status: String(res.status) });
}
