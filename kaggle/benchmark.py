"""Small repeatable CPU load test against a running Todo List API."""

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


EXPECTED_STATUS = {"POST": 201, "GET": 200, "DELETE": 204}


def request(base_url, method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
    latency_ms = (time.perf_counter() - start) * 1000
    parsed = json.loads(payload) if payload else None
    return status, parsed, latency_ms


def prepare_user(base_url):
    email = f"bench-{uuid.uuid4().hex}@example.com"
    status, _, _ = request(
        base_url, "POST", "/api/auth/register", {"email": email, "password": "benchmark-pass-123"}
    )
    if status != 201:
        raise RuntimeError(f"Registration failed: HTTP {status}")
    status, body, _ = request(
        base_url, "POST", "/api/auth/login", {"email": email, "password": "benchmark-pass-123"}
    )
    if status != 200:
        raise RuntimeError(f"Login failed: HTTP {status}")
    return body["access_token"]


def worker(base_url, token, iterations, worker_id):
    measurements = []
    completed_cycles = 0
    skipped_requests = 0

    def record(iteration, method, status, latency):
        measurements.append({
            "worker_id": worker_id,
            "iteration": iteration,
            "method": method,
            "status": status,
            "latency_ms": latency,
            "success": status == EXPECTED_STATUS[method],
        })

    for index in range(iterations):
        status, task, latency = request(
            base_url, "POST", "/api/tasks", {"title": f"Benchmark task {index}"}, token
        )
        record(index, "POST", status, latency)
        if status != 201:
            skipped_requests += 2
            continue
        task_id = task["id"]
        status, tasks, latency = request(base_url, "GET", "/api/tasks", token=token)
        record(index, "GET", status, latency)
        task_visible = status == 200 and any(item["id"] == task_id for item in tasks)
        status, _, latency = request(base_url, "DELETE", f"/api/tasks/{task_id}", token=token)
        record(index, "DELETE", status, latency)
        if task_visible and status == 204:
            completed_cycles += 1
    return {
        "measurements": measurements,
        "completed_cycles": completed_cycles,
        "skipped_requests": skipped_requests,
    }


def percentile(values, percent):
    values = sorted(values)
    index = round((len(values) - 1) * percent / 100)
    return values[index]


def summarize(results, duration, concurrency, iterations):
    """Aggregate measured task requests; registration/login are excluded."""
    measurements = [item for result in results for item in result["measurements"]]
    attempted = len(measurements)
    successful = sum(item["success"] for item in measurements)
    completed = sum(result["completed_cycles"] for result in results)
    methods = {}
    for method in EXPECTED_STATUS:
        latencies = [item["latency_ms"] for item in measurements if item["method"] == method]
        methods[method] = {
            "n": len(latencies),
            "mean_ms": statistics.mean(latencies) if latencies else None,
            "p50_ms": percentile(latencies, 50) if latencies else None,
            "p95_ms": percentile(latencies, 95) if latencies else None,
        }
    return {
        "concurrency": concurrency,
        "iterations": iterations,
        "duration_seconds": duration,
        "throughput_rps": attempted / duration if duration > 0 else None,
        "expected_requests": 3 * concurrency * iterations,
        "attempted_requests": attempted,
        "successful_requests": successful,
        "failed_requests": attempted - successful,
        "skipped_requests": sum(result["skipped_requests"] for result in results),
        "expected_cycles": concurrency * iterations,
        "completed_cycles": completed,
        "incomplete_cycles": concurrency * iterations - completed,
        "methods": methods,
        "measurements": measurements,
    }


def print_report(report):
    print(f"Concurrency: {report['concurrency']}; cycles/user: {report['iterations']}")
    throughput = report["throughput_rps"]
    throughput_text = f"{throughput:.1f}" if throughput is not None else "n/a"
    print(f"Elapsed: {report['duration_seconds']:.2f}s; throughput: {throughput_text} req/s")
    for key in (
        "expected_requests", "attempted_requests", "successful_requests", "failed_requests",
        "skipped_requests", "expected_cycles", "completed_cycles", "incomplete_cycles",
    ):
        print(f"{key}: {report[key]}")
    for method, stats in report["methods"].items():
        if stats["n"]:
            print(
                f"{method:6} n={stats['n']:4} "
                f"mean={stats['mean_ms']:7.1f}ms "
                f"p50={stats['p50_ms']:7.1f}ms "
                f"p95={stats['p95_ms']:7.1f}ms"
            )
    print(f"HTTP failures: {report['failed_requests']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=25, help="Create/list/delete cycles per user")
    parser.add_argument("--output-json", type=Path, help="Save summary and per-request measurements as JSON")
    args = parser.parse_args()
    if args.concurrency < 1 or args.iterations < 1:
        parser.error("concurrency and iterations must be positive")
    base_url = args.base_url.rstrip("/")

    tokens = [prepare_user(base_url) for _ in range(args.concurrency)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(
            lambda pair: worker(base_url, pair[1], args.iterations, pair[0]), enumerate(tokens)
        ))
    duration = time.perf_counter() - started
    report = summarize(results, duration, args.concurrency, args.iterations)
    print_report(report)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if report["failed_requests"] or report["incomplete_cycles"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
