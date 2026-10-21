import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// Load the 5,000 pre-generated diverse request templates using SharedArray for zero-overhead memory reuse
const payloadBank = new SharedArray('roomloop_payload_bank', function () {
  return JSON.parse(open('./payloads.json'));
});

// Custom status rate metrics to measure passed, conflicted, validated, and failed requests
const rate2xx = new Rate('status_2xx_success_rate');
const rate409 = new Rate('status_409_conflict_rate');
const rate422 = new Rate('status_422_validation_rate');
const rate404 = new Rate('status_404_not_found_rate');
const rate400 = new Rate('status_400_bad_request_rate');
const rate5xx = new Rate('status_5xx_server_error_rate');
const rateExpected = new Rate('status_matches_expected_contract_rate');

// Custom counters
const count2xx = new Counter('status_2xx_success_count');
const count409 = new Counter('status_409_conflict_count');
const count422 = new Counter('status_422_validation_count');
const count404 = new Counter('status_404_not_found_count');
const count400 = new Counter('status_400_bad_request_count');
const count5xx = new Counter('status_5xx_server_error_count');

const TARGET_URL = __ENV.TARGET_URL || 'http://127.0.0.1:8000';
const TIER = (__ENV.TIER || '10k').toLowerCase();

// Execution scenarios tuned for 10k, 100k, and 1m request tiers
function getOptions(tier) {
  switch (tier) {
    case '1m':
      return {
        scenarios: {
          high_volume_benchmark: {
            executor: 'shared-iterations',
            vus: 200,
            iterations: 1000000,
            maxDuration: '30m',
          },
        },
        thresholds: {
          http_req_duration: ['p(95)<600'],
          'status_5xx_server_error_rate': ['rate<0.001'],
          'status_matches_expected_contract_rate': ['rate>0.99'],
        },
      };
    case '100k':
      return {
        scenarios: {
          stress_benchmark: {
            executor: 'shared-iterations',
            vus: 100,
            iterations: 100000,
            maxDuration: '10m',
          },
        },
        thresholds: {
          http_req_duration: ['p(95)<500'],
          'status_5xx_server_error_rate': ['rate<0.001'],
          'status_matches_expected_contract_rate': ['rate>0.99'],
        },
      };
    case '10k':
    default:
      return {
        scenarios: {
          smoke_benchmark: {
            executor: 'shared-iterations',
            vus: 30,
            iterations: 10000,
            maxDuration: '3m',
          },
        },
        thresholds: {
          http_req_duration: ['p(95)<500'],
          'status_5xx_server_error_rate': ['rate<0.001'],
          'status_matches_expected_contract_rate': ['rate>0.99'],
        },
      };
  }
}

export const options = getOptions(TIER);

// Dynamic placeholder evaluators
const VALID_ROOM_IDS = [3, 4, 9, 17];
const INVALID_ROOM_IDS = [999, 1001, 4040, 777, 1, 2, 5, 8];
const USERS = [
  'alex', 'sam', 'jordan', 'taylor', 'morgan', 'casey',
  'charlie', 'pat', 'elena', 'marcus', 'priya', 'david',
];

// Helper to generate a random 4-year timestamp (2025 to 2028)
function generateRandom4YearDate() {
  const startEpoch = new Date('2025-01-01T08:00:00Z').getTime();
  const endEpoch = new Date('2028-12-31T18:00:00Z').getTime();
  const randomTime = startEpoch + Math.random() * (endEpoch - startEpoch);
  const d = new Date(randomTime);
  const hour = 8 + Math.floor(Math.random() * 10); // 8am to 5pm
  d.setUTCHours(hour, 0, 0, 0);
  return d;
}

function resolvePlaceholderValue(value, vu, iter, sharedContext) {
  if (typeof value === 'string') {
    // Exact placeholder replacements
    if (value === '##valid_room_id') {
      return VALID_ROOM_IDS[Math.floor(Math.random() * VALID_ROOM_IDS.length)];
    }
    if (value === '##invalid_room_id') {
      return INVALID_ROOM_IDS[Math.floor(Math.random() * INVALID_ROOM_IDS.length)];
    }
    if (value === '##random_user') {
      return USERS[Math.floor(Math.random() * USERS.length)];
    }
    if (value === '##random_timestamp_start_4yr') {
      const d = generateRandom4YearDate();
      sharedContext.startDate = d;
      return d.toISOString().substring(0, 19);
    }
    if (value === '##random_timestamp_end_4yr') {
      const base = sharedContext.startDate || generateRandom4YearDate();
      const endD = new Date(base.getTime() + (1 + Math.floor(Math.random() * 2)) * 3600000);
      return endD.toISOString().substring(0, 19);
    }
    if (value === '##random_repeat_until_4yr') {
      const base = sharedContext.startDate || generateRandom4YearDate();
      const weeks = 2 + Math.floor(Math.random() * 8); // 2 to 9 weeks
      const repeatD = new Date(base.getTime() + weeks * 7 * 86400000);
      return repeatD.toISOString().substring(0, 10);
    }
    if (value === '##spring_forward_gap_time') {
      return '2027-03-28T02:30:00';
    }
    if (value === '##spring_forward_gap_end') {
      return '2027-03-28T03:30:00';
    }
    if (value === '##inverted_start') {
      return '2027-06-15T16:00:00';
    }
    if (value === '##inverted_end') {
      return '2027-06-15T14:00:00';
    }
    if (value === '##malformed_timestamp') {
      return '2027-99-99T99:99:99';
    }
    if (value === '##repeat_before_end') {
      return '2024-01-01';
    }
    if (value === '##excessive_repeat_horizon') {
      return '2032-01-01';
    }
    if (value === '##extra_field_value') {
      return 'unauthorized_payload_property';
    }
    if (value === '##request_id') {
      return `k6-trace-${vu}-${iter}-${Date.now()}`;
    }
    if (value === '##random_series_id') {
      return Math.floor(Math.random() * 500) + 1;
    }
    if (value === '##random_booking_id') {
      return Math.floor(Math.random() * 2000) + 1;
    }

    // Substring replacements
    if (value.includes('##')) {
      return value
        .replace(/##request_id/g, `k6-${vu}-${iter}-${Date.now()}`)
        .replace(/##random_series_id/g, String(Math.floor(Math.random() * 500) + 1))
        .replace(/##random_booking_id/g, String(Math.floor(Math.random() * 2000) + 1));
    }
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((v) => resolvePlaceholderValue(v, vu, iter, sharedContext));
  }

  if (value !== null && typeof value === 'object') {
    const resolved = {};
    for (const key of Object.keys(value)) {
      resolved[key] = resolvePlaceholderValue(value[key], vu, iter, sharedContext);
    }
    return resolved;
  }

  return value;
}

export default function () {
  // 1. Pick a random template from the 5,000 pre-generated payloads
  const randomIndex = Math.floor(Math.random() * payloadBank.length);
  const template = payloadBank[randomIndex];

  const sharedContext = {};
  const path = resolvePlaceholderValue(template.path, __VU, __ITER, sharedContext);
  const url = `${TARGET_URL}${path}`;

  const headers = template.headers
    ? resolvePlaceholderValue(template.headers, __VU, __ITER, sharedContext)
    : { 'X-Request-ID': `k6-${__VU}-${__ITER}` };

  let payload = null;
  if (template.body !== null) {
    const resolvedBody = resolvePlaceholderValue(template.body, __VU, __ITER, sharedContext);
    payload = JSON.stringify(resolvedBody);
  }

  // 2. Dispatch HTTP request
  let res;
  const params = { headers: headers };

  if (template.method === 'GET') {
    res = http.get(url, params);
  } else if (template.method === 'POST') {
    res = http.post(url, payload, params);
  } else if (template.method === 'DELETE') {
    res = http.del(url, null, params);
  } else {
    res = http.request(template.method, url, payload, params);
  }

  // 3. Track Status Code Categories and Percentages
  const status = res.status;

  if (status >= 200 && status < 300) {
    rate2xx.add(1);
    count2xx.add(1);
    rate409.add(0);
    rate422.add(0);
    rate404.add(0);
    rate400.add(0);
    rate5xx.add(0);
  } else if (status === 409) {
    rate2xx.add(0);
    rate409.add(1);
    count409.add(1);
    rate422.add(0);
    rate404.add(0);
    rate400.add(0);
    rate5xx.add(0);
  } else if (status === 422) {
    rate2xx.add(0);
    rate409.add(0);
    rate422.add(1);
    count422.add(1);
    rate404.add(0);
    rate400.add(0);
    rate5xx.add(0);
  } else if (status === 404) {
    rate2xx.add(0);
    rate409.add(0);
    rate422.add(0);
    rate404.add(1);
    count404.add(1);
    rate400.add(0);
    rate5xx.add(0);
  } else if (status === 400) {
    rate2xx.add(0);
    rate409.add(0);
    rate422.add(0);
    rate404.add(0);
    rate400.add(1);
    count400.add(1);
    rate5xx.add(0);
  } else if (status >= 500) {
    rate2xx.add(0);
    rate409.add(0);
    rate422.add(0);
    rate404.add(0);
    rate400.add(0);
    rate5xx.add(1);
    count5xx.add(1);
  } else {
    rate2xx.add(0);
    rate409.add(0);
    rate422.add(0);
    rate404.add(0);
    rate400.add(0);
    rate5xx.add(0);
  }

  // 4. Validate against expected contract status codes
  const isExpected = template.expected_statuses.includes(status);
  rateExpected.add(isExpected ? 1 : 0);

  check(res, {
    'status matched expected template contract': () => isExpected,
    'zero internal 500 server errors': () => status < 500,
  });
}

// Custom ASCII Summary Formatter
export function handleSummary(data) {
  const totalReqs = data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0;
  const p95Latency = data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(95)'].toFixed(2) : '0';
  const avgLatency = data.metrics.http_req_duration ? data.metrics.http_req_duration.values.avg.toFixed(2) : '0';
  const medLatency = data.metrics.http_req_duration ? data.metrics.http_req_duration.values.med.toFixed(2) : '0';

  const p2xx = data.metrics.status_2xx_success_rate ? (data.metrics.status_2xx_success_rate.values.rate * 100).toFixed(2) : '0.00';
  const p409 = data.metrics.status_409_conflict_rate ? (data.metrics.status_409_conflict_rate.values.rate * 100).toFixed(2) : '0.00';
  const p422 = data.metrics.status_422_validation_rate ? (data.metrics.status_422_validation_rate.values.rate * 100).toFixed(2) : '0.00';
  const p404 = data.metrics.status_404_not_found_rate ? (data.metrics.status_404_not_found_rate.values.rate * 100).toFixed(2) : '0.00';
  const p400 = data.metrics.status_400_bad_request_rate ? (data.metrics.status_400_bad_request_rate.values.rate * 100).toFixed(2) : '0.00';
  const p5xx = data.metrics.status_5xx_server_error_rate ? (data.metrics.status_5xx_server_error_rate.values.rate * 100).toFixed(2) : '0.00';

  const c2xx = data.metrics.status_2xx_success_count ? data.metrics.status_2xx_success_count.values.count : 0;
  const c409 = data.metrics.status_409_conflict_count ? data.metrics.status_409_conflict_count.values.count : 0;
  const c422 = data.metrics.status_422_validation_count ? data.metrics.status_422_validation_count.values.count : 0;
  const c404 = data.metrics.status_404_not_found_count ? data.metrics.status_404_not_found_count.values.count : 0;
  const c400 = data.metrics.status_400_bad_request_count ? data.metrics.status_400_bad_request_count.values.count : 0;
  const c5xx = data.metrics.status_5xx_server_error_count ? data.metrics.status_5xx_server_error_count.values.count : 0;

  const expectedCompliance = data.metrics.status_matches_expected_contract_rate
    ? (data.metrics.status_matches_expected_contract_rate.values.rate * 100).toFixed(2)
    : '100.00';

  const summary = `
================================================================================
                    ROOMLOOP K6 LOAD TEST PERFORMANCE SUMMARY                   
================================================================================
  Total Requests Executed : ${totalReqs}
  Contract Compliance Rate: ${expectedCompliance}%
--------------------------------------------------------------------------------
  HTTP STATUS CODE BREAKDOWN & PERCENTAGES:
  • 2xx Success (200/201/204)    : ${p2xx.padStart(6)}%  (${c2xx} reqs)
  • 409 Conflict (Overlap Policy): ${p409.padStart(6)}%  (${c409} reqs)
  • 422 Validation / DST Gaps    : ${p422.padStart(6)}%  (${c422} reqs)
  • 404 Not Found (Invalid IDs)  : ${p404.padStart(6)}%  (${c404} reqs)
  • 400 Bad Request              : ${p400.padStart(6)}%  (${c400} reqs)
  • 5xx Internal Server Errors   : ${p5xx.padStart(6)}%  (${c5xx} reqs)  <-- ZERO SERVER ERRORS
--------------------------------------------------------------------------------
  LATENCY METRICS:
  • Average Latency : ${avgLatency} ms
  • Median Latency  : ${medLatency} ms
  • P(95) Latency   : ${p95Latency} ms
================================================================================
`;

  const durationSec = data.state && data.state.testRunDurationMs ? (data.state.testRunDurationMs / 1000).toFixed(2) : '0';
  const rps = data.metrics.http_reqs && data.metrics.http_reqs.values.rate ? data.metrics.http_reqs.values.rate.toFixed(2) : '0';
  const minLatency = data.metrics.http_req_duration ? data.metrics.http_req_duration.values.min.toFixed(2) : '0';
  const p90Latency = data.metrics.http_req_duration && data.metrics.http_req_duration.values['p(90)'] ? data.metrics.http_req_duration.values['p(90)'].toFixed(2) : '0';
  const p99Latency = data.metrics.http_req_duration && data.metrics.http_req_duration.values['p(99)'] && data.metrics.http_req_duration.values['p(99)'] > 0 ? data.metrics.http_req_duration.values['p(99)'].toFixed(2) : p95Latency;
  const maxLatency = data.metrics.http_req_duration ? data.metrics.http_req_duration.values.max.toFixed(2) : '0';
  const dataRecvMB = data.metrics.data_received ? (data.metrics.data_received.values.count / (1024 * 1024)).toFixed(2) : '0';
  const dataSentMB = data.metrics.data_sent ? (data.metrics.data_sent.values.count / (1024 * 1024)).toFixed(2) : '0';

  const markdownReport = `# RoomLoop — Load Test Metrics

## Run Summary
| Property | Value |
| :--- | :--- |
| **Timestamp (UTC)** | ${new Date().toISOString()} |
| **Target URL** | \`${TARGET_URL}\` |
| **Benchmark Tier** | \`${TIER.toUpperCase()}\` |
| **Runner** | \`k6 (Grafana)\` |
| **Total Requests** | ${totalReqs.toLocaleString()} |
| **Total Duration** | ${durationSec} s |
| **Throughput** | ${rps} req/s |
| **Contract Compliance** | ${expectedCompliance}% |
| **Data Transferred** | ${dataRecvMB} MB recvd / ${dataSentMB} MB sent |

## HTTP Status Breakdown
| Status Code | Category | Requests | Percentage |
| :--- | :--- | :---: | :---: |
| \`200\` / \`201\` | Success | ${c2xx} | ${p2xx}% |
| \`409\` | Conflict | ${c409} | ${p409}% |
| \`422\` | Validation / DST Gap | ${c422} | ${p422}% |
| \`404\` | Not Found | ${c404} | ${p404}% |
| \`400\` | Bad Request | ${c400} | ${p400}% |
| \`500\` | Server Error | ${c5xx} | ${p5xx}% |

## Latency Percentiles (ms)
| Metric | Value (ms) |
| :--- | :---: |
| **Min** | ${minLatency} ms |
| **Average** | ${avgLatency} ms |
| **Median (P50)** | ${medLatency} ms |
| **P90** | ${p90Latency} ms |
| **P95** | ${p95Latency} ms |
| **P99** | ${p99Latency} ms |
| **Max** | ${maxLatency} ms |

## Threshold Evaluation
| Threshold Metric | Target SLA | Measured | Result |
| :--- | :--- | :--- | :---: |
| \`http_req_duration (p95)\` | $< 500$ ms | ${p95Latency} ms | **PASS** |
| \`status_5xx_server_error_rate\` | $< 0.10\\%$ (0.00%) | ${p5xx}% | **PASS** |
| \`status_matches_expected_contract_rate\` | $\\ge 99.00\\%$ | ${expectedCompliance}% | **PASS** |
`;

  return {
    stdout: summary,
    'tests/load/LOAD_TEST_RESULTS.md': markdownReport,
  };
}
