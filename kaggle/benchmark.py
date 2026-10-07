"""Small repeatable CPU load test against a running Todo List API."""

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor


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


def worker(base_url, token, iterations):
    measurements = []
    for index in range(iterations):
        status, task, latency = request(
            base_url, "POST", "/api/tasks", {"title": f"Benchmark task {index}"}, token
        )
        measurements.append(("POST", status, latency))
        if status != 201:
            continue
        task_id = task["id"]
        status, tasks, latency = request(base_url, "GET", "/api/tasks", token=token)
        measurements.append(("GET", status, latency))
        if status == 200 and not any(item["id"] == task_id for item in tasks):
            raise RuntimeError("Created task missing from list")
        status, _, latency = request(base_url, "DELETE", f"/api/tasks/{task_id}", token=token)
        measurements.append(("DELETE", status, latency))
    return measurements


def percentile(values, percent):
    values = sorted(values)
    index = round((len(values) - 1) * percent / 100)
    return values[index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=25, help="Create/list/delete cycles per user")
    args = parser.parse_args()
    if args.concurrency < 1 or args.iterations < 1:
        parser.error("concurrency and iterations must be positive")
    base_url = args.base_url.rstrip("/")

    tokens = [prepare_user(base_url) for _ in range(args.concurrency)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda token: worker(base_url, token, args.iterations), tokens))
    duration = time.perf_counter() - started
    measurements = [item for result in results for item in result]
    expected = {"POST": 201, "GET": 200, "DELETE": 204}
    failures = [(method, status) for method, status, _ in measurements if status != expected[method]]

    print(f"Concurrency: {args.concurrency}; cycles/user: {args.iterations}")
    print(f"Elapsed: {duration:.2f}s; requests: {len(measurements)}; throughput: {len(measurements) / duration:.1f} req/s")
    for method in ("POST", "GET", "DELETE"):
        latencies = [latency for name, _, latency in measurements if name == method]
        if latencies:
            print(
                f"{method:6} n={len(latencies):4} "
                f"mean={statistics.mean(latencies):7.1f}ms "
                f"p50={percentile(latencies, 50):7.1f}ms "
                f"p95={percentile(latencies, 95):7.1f}ms"
            )
    print(f"HTTP failures: {len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
