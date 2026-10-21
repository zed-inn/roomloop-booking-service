# RoomLoop — Load Test Metrics

## Run Summary
| Property | Value |
| :--- | :--- |
| **Timestamp (UTC)** | 2026-10-21T20:00:37.658Z |
| **Target URL** | `http://127.0.0.1:8095` |
| **Benchmark Tier** | `10K` |
| **Runner** | `k6 (Grafana)` |
| **Total Requests** | 10000 |
| **Total Duration** | 31.62 s |
| **Throughput** | 316.24 req/s |
| **Contract Compliance** | 100.00% |
| **Data Transferred** | 2.88 MB recvd / 1.80 MB sent |

## HTTP Status Breakdown
| Status Code | Category | Requests | Percentage |
| :--- | :--- | :---: | :---: |
| `200` / `201` | Success | 5997 | 59.97% |
| `409` | Conflict | 2895 | 28.95% |
| `422` | Validation / DST Gap | 467 | 4.67% |
| `404` | Not Found | 599 | 5.99% |
| `400` | Bad Request | 42 | 0.42% |
| `500` | Server Error | 0 | 0.00% |

## Latency Percentiles (ms)
| Metric | Value (ms) |
| :--- | :---: |
| **Min** | 15.17 ms |
| **Average** | 94.27 ms |
| **Median (P50)** | 85.58 ms |
| **P90** | 130.17 ms |
| **P95** | 155.56 ms |
| **P99** | 155.56 ms |
| **Max** | 409.81 ms |

## Threshold Evaluation
| Threshold Metric | Target SLA | Measured | Result |
| :--- | :--- | :--- | :---: |
| `http_req_duration (p95)` | $< 500$ ms | 155.56 ms | **PASS** |
| `status_5xx_server_error_rate` | $< 0.10\%$ (0.00%) | 0.00% | **PASS** |
| `status_matches_expected_contract_rate` | $\ge 99.00\%$ | 100.00% | **PASS** |
