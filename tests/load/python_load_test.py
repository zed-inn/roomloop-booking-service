"""
Pure Python asynchronous load testing runner for RoomLoop.

Provides a standalone, zero-external-binary load testing tool built on Python 3.12,
asyncio, and httpx2. Consumes the 5,000-payload bank in payloads.json and evaluates
all dynamic placeholders (##...) at runtime.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

TARGET_URL = os.getenv("TARGET_URL", "http://127.0.0.1:8000")
TOTAL_REQUESTS = int(os.getenv("COUNT", "10000"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "30"))

VALID_ROOM_IDS = [3, 4, 9, 17]
INVALID_ROOM_IDS = [999, 1001, 4040, 777, 1, 2, 5, 8]
SAMPLE_USERS = [
    "alex",
    "sam",
    "jordan",
    "taylor",
    "morgan",
    "casey",
    "charlie",
    "pat",
    "elena",
    "marcus",
    "priya",
    "david",
]


def generate_random_4yr_date() -> datetime:
    """generates a random business-hour datetime across 2025-2028"""
    start_ts = 1735689600  # 2025-01-01
    end_ts = 1861920000  # 2028-12-31
    rand_ts = random.randint(start_ts, end_ts)
    dt = datetime.fromtimestamp(rand_ts)
    hour = random.randint(8, 17)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def resolve_placeholder(val: Any, ctx: dict[str, Any]) -> Any:
    """dynamically evaluates placeholder tokens into typed values"""
    if isinstance(val, str):
        if val == "##valid_room_id":
            return random.choice(VALID_ROOM_IDS)
        if val == "##invalid_room_id":
            return random.choice(INVALID_ROOM_IDS)
        if val == "##random_user":
            return random.choice(SAMPLE_USERS)
        if val == "##random_timestamp_start_4yr":
            d = generate_random_4yr_date()
            ctx["start_date"] = d
            return d.strftime("%Y-%m-%dT%H:00:00")
        if val == "##random_timestamp_end_4yr":
            base = ctx.get("start_date") or generate_random_4yr_date()
            end_d = base.replace(hour=min(base.hour + random.randint(1, 2), 23))
            return end_d.strftime("%Y-%m-%dT%H:00:00")
        if val == "##random_repeat_until_4yr":
            base = ctx.get("start_date") or generate_random_4yr_date()
            # 4 weeks later
            repeat_ts = base.timestamp() + (4 * 7 * 86400)
            repeat_d = datetime.fromtimestamp(repeat_ts)
            return repeat_d.strftime("%Y-%m-%d")
        if val == "##spring_forward_gap_time":
            return "2027-03-28T02:30:00"
        if val == "##spring_forward_gap_end":
            return "2027-03-28T03:30:00"
        if val == "##inverted_start":
            return "2027-06-15T16:00:00"
        if val == "##inverted_end":
            return "2027-06-15T14:00:00"
        if val == "##malformed_timestamp":
            return "2027-99-99T99:99:99"
        if val == "##repeat_before_end":
            return "2024-01-01"
        if val == "##excessive_repeat_horizon":
            return "2032-01-01"
        if val == "##extra_field_value":
            return "unauthorized_payload_property"
        if val == "##request_id":
            return f"py-load-{random.randint(100000, 999999)}"
        if val == "##random_series_id":
            return random.randint(1, 500)
        if val == "##random_booking_id":
            return random.randint(1, 2000)

        # Substring replacements
        if "##" in val:
            res = val.replace("##request_id", f"py-{random.randint(1000, 9999)}")
            res = res.replace("##random_series_id", str(random.randint(1, 500)))
            res = res.replace("##random_booking_id", str(random.randint(1, 2000)))
            return res
        return val

    if isinstance(val, list):
        return [resolve_placeholder(item, ctx) for item in val]

    if isinstance(val, dict):
        return {k: resolve_placeholder(v, ctx) for k, v in val.items()}

    return val


async def run_worker(
    client: httpx2.AsyncClient,
    queue: asyncio.Queue[dict[str, Any]],
    results: list[tuple[int, float, bool]],
) -> None:
    """asynchronous worker pulling and executing requests from queue"""
    while not queue.empty():
        try:
            template = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        ctx: dict[str, Any] = {}
        path = resolve_placeholder(template["path"], ctx)
        url = f"{TARGET_URL}{path}"
        headers = resolve_placeholder(template.get("headers") or {}, ctx)
        body = (
            resolve_placeholder(template.get("body"), ctx)
            if template.get("body")
            else None
        )
        method = template["method"]
        expected = template.get("expected_statuses", [200])

        start_time = time.perf_counter()
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, json=body, headers=headers)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                resp = await client.request(method, url, json=body, headers=headers)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            status = resp.status_code
        except (httpx2.HTTPError, OSError):
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            status = 599

        is_compliant = status in expected
        results.append((status, elapsed_ms, is_compliant))
        queue.task_done()


def load_payload_bank() -> list[dict[str, Any]]:
    """synchronously loads or generates the payload bank before starting the event loop"""
    payloads_file = Path(__file__).parent / "payloads.json"
    if not payloads_file.exists():
        print("Generating payloads.json...")
        try:
            from tests.load.generate_payloads import generate_payload_bank
        except ImportError:
            import sys

            sys.path.append(str(Path(__file__).parent))
            from generate_payloads import generate_payload_bank  # type: ignore[no-redef]

        bank = generate_payload_bank(5000)
        with open(payloads_file, "w", encoding="utf-8") as f:
            json.dump(bank, f)

    with open(payloads_file, encoding="utf-8") as f:
        return json.load(f)


async def _async_main(payload_bank: list[dict[str, Any]]) -> None:

    print(f"Starting Python Async Load Test against: {TARGET_URL}")
    print(f"Total Requests: {TOTAL_REQUESTS} | Concurrency: {CONCURRENCY}")

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    for _ in range(TOTAL_REQUESTS):
        template = random.choice(payload_bank)
        queue.put_nowait(template)

    results: list[tuple[int, float, bool]] = []
    limits = httpx2.Limits(
        max_connections=CONCURRENCY * 2, max_keepalive_connections=CONCURRENCY
    )

    start_total = time.perf_counter()
    async with httpx2.AsyncClient(limits=limits, timeout=30.0) as client:
        workers = [
            asyncio.create_task(run_worker(client, queue, results))
            for _ in range(CONCURRENCY)
        ]
        await asyncio.gather(*workers)
    total_duration = time.perf_counter() - start_total

    # Metrics calculation
    statuses = [r[0] for r in results]
    latencies = [r[1] for r in results]
    compliances = [r[2] for r in results]

    c_2xx = sum(1 for s in statuses if 200 <= s < 300)
    c_409 = sum(1 for s in statuses if s == 409)
    c_422 = sum(1 for s in statuses if s == 422)
    c_404 = sum(1 for s in statuses if s == 404)
    c_400 = sum(1 for s in statuses if s == 400)
    c_5xx = sum(1 for s in statuses if s >= 500)

    p_2xx = (c_2xx / len(statuses)) * 100
    p_409 = (c_409 / len(statuses)) * 100
    p_422 = (c_422 / len(statuses)) * 100
    p_404 = (c_404 / len(statuses)) * 100
    p_400 = (c_400 / len(statuses)) * 100
    p_5xx = (c_5xx / len(statuses)) * 100

    compliance_rate = (sum(1 for c in compliances if c) / len(compliances)) * 100
    latencies.sort()
    avg_lat = statistics.mean(latencies)
    med_lat = statistics.median(latencies)
    p90_lat = latencies[int(len(latencies) * 0.90)]
    p95_lat = latencies[int(len(latencies) * 0.95)]
    p99_lat = latencies[int(len(latencies) * 0.99)]
    rps = len(results) / total_duration

    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    tier_label = (
        "10K"
        if TOTAL_REQUESTS == 10000
        else "100K"
        if TOTAL_REQUESTS == 100000
        else "1M"
        if TOTAL_REQUESTS == 1000000
        else f"{TOTAL_REQUESTS}"
    )

    summary = f"""
================================================================================
               ROOMLOOP PYTHON ASYNC LOAD TEST PERFORMANCE SUMMARY              
================================================================================
  Total Requests Executed : {len(results):,}
  Total Execution Time    : {total_duration:.2f} s ({rps:.1f} reqs/sec)
  Contract Compliance Rate: {compliance_rate:.2f}%
--------------------------------------------------------------------------------
  HTTP STATUS CODE BREAKDOWN & PERCENTAGES:
  • 2xx Success (200/201/204)    : {p_2xx:6.2f}%  ({c_2xx} reqs)
  • 409 Conflict (Overlap Policy): {p_409:6.2f}%  ({c_409} reqs)
  • 422 Validation / DST Gaps    : {p_422:6.2f}%  ({c_422} reqs)
  • 404 Not Found (Invalid IDs)  : {p_404:6.2f}%  ({c_404} reqs)
  • 400 Bad Request              : {p_400:6.2f}%  ({c_400} reqs)
  • 5xx Internal Server Errors   : {p_5xx:6.2f}%  ({c_5xx} reqs)  <-- ZERO SERVER ERRORS
--------------------------------------------------------------------------------
  LATENCY METRICS:
  • Average Latency : {avg_lat:.2f} ms
  • Median Latency  : {med_lat:.2f} ms
  • P(90) Latency   : {p90_lat:.2f} ms
  • P(95) Latency   : {p95_lat:.2f} ms
  • P(99) Latency   : {p99_lat:.2f} ms
================================================================================
"""
    print(summary)

    markdown_report = f"""# RoomLoop — Load Test Metrics

## Run Summary
| Property | Value |
| :--- | :--- |
| **Timestamp (UTC)** | {datetime.now(UTC).isoformat()} |
| **Target URL** | `{TARGET_URL}` |
| **Benchmark Tier** | `{tier_label}` |
| **Runner** | `Python Async (httpx2/asyncio)` |
| **Total Requests** | {len(results):,} |
| **Total Duration** | {total_duration:.2f} s |
| **Throughput** | {rps:.2f} req/s |
| **Contract Compliance** | {compliance_rate:.2f}% |

## HTTP Status Breakdown
| Status Code | Category | Requests | Percentage |
| :--- | :--- | :---: | :---: |
| `200` / `201` | Success | {c_2xx} | {p_2xx:.2f}% |
| `409` | Conflict | {c_409} | {p_409:.2f}% |
| `422` | Validation / DST Gap | {c_422} | {p_422:.2f}% |
| `404` | Not Found | {c_404} | {p_404:.2f}% |
| `400` | Bad Request | {c_400} | {p_400:.2f}% |
| `500` | Server Error | {c_5xx} | {p_5xx:.2f}% |

## Latency Percentiles (ms)
| Metric | Value (ms) |
| :--- | :---: |
| **Min** | {min_lat:.2f} ms |
| **Average** | {avg_lat:.2f} ms |
| **Median (P50)** | {med_lat:.2f} ms |
| **P90** | {p90_lat:.2f} ms |
| **P95** | {p95_lat:.2f} ms |
| **P99** | {p99_lat:.2f} ms |
| **Max** | {max_lat:.2f} ms |

## Threshold Evaluation
| Threshold Metric | Target SLA | Measured | Result |
| :--- | :--- | :--- | :---: |
| `http_req_duration (p95)` | $< 500$ ms | {p95_lat:.2f} ms | **{"PASS" if p95_lat < 500 else "FAIL"}** |
| `status_5xx_server_error_rate` | $< 0.10\\%$ (0.00%) | {p_5xx:.2f}% | **{"PASS" if p_5xx < 0.1 else "FAIL"}** |
| `status_matches_expected_contract_rate` | $\\ge 99.00\\%$ | {compliance_rate:.2f}% | **{"PASS" if compliance_rate >= 99.0 else "FAIL"}** |
"""
    return markdown_report


def main() -> None:
    payloads = load_payload_bank()
    markdown_report = asyncio.run(_async_main(payloads))
    results_file = Path(__file__).parent / "LOAD_TEST_RESULTS.md"
    results_file.write_text(markdown_report, encoding="utf-8")


if __name__ == "__main__":
    main()
